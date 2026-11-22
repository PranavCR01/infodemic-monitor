"""OCR and page text extraction (§6 "Building the library" step 2).

OCRmyPDF (Tesseract) deskews each page and writes a text layer into the PDF; PyMuPDF then
extracts the text page by page. Tesseract's layout analysis keeps two-column papers in
reading order, and PyMuPDF reads the text layer in the order Tesseract wrote it.

Every page gets two quality signals:

- ``confidence``: the mean Tesseract word confidence (0–100) from a second, cheap pass
  over the deskewed page (``tesseract … tsv``), because OCRmyPDF doesn't report one. None
  when Tesseract isn't available (text-layer-only extraction).
- ``word_ratio``: the share of tokens that look like words. A crude, engine-free check
  that also catches garbage text layers in PDFs that were never OCRed by us.

A page below either threshold is *flagged*: kept out of the index until someone checks it
(``LibraryIngestor.approve_pages``). A page with almost no text is *blank*, not flagged.

The heavy tools (``ocrmypdf``, ``tesseract``, ``pymupdf``) are imported lazily, so the
rest of the retrieval package works without them.
"""
from __future__ import annotations

import csv
import io
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, Optional, Protocol, Sequence

from app.core.retrieval.library.config import OcrConfig

PageStatus = Literal["ok", "flagged", "blank"]

_TOKEN = re.compile(r"\S+")
_WORDLIKE = re.compile(r"^[\(\[\"'“‘]*(?:[A-Za-z][A-Za-z'’\-]*|\d+(?:[.,]\d+)*%?|[A-Za-z]+\d+[A-Za-z\d]*)[\)\]\"'”’.,;:!?%]*$")


@dataclass(frozen=True)
class PageText:
    page: int  # 1-based
    text: str
    confidence: Optional[float] = None  # mean Tesseract word confidence, 0–100
    word_ratio: float = 1.0
    status: PageStatus = "ok"
    reason: str = ""


class OcrEngine(Protocol):
    """Turns one PDF into per-page text with quality signals."""

    name: str

    def extract(self, pdf_path: Path) -> list[PageText]: ...


def word_ratio(text: str) -> float:
    tokens = _TOKEN.findall(text)
    if not tokens:
        return 0.0
    return sum(1 for t in tokens if _WORDLIKE.match(t)) / len(tokens)


def assess_page(page: int, text: str, confidence: Optional[float], cfg: OcrConfig) -> PageText:
    """Apply the flagging rules to one page."""
    ratio = word_ratio(text)
    chars = len(re.sub(r"\s", "", text))
    if chars < cfg.min_page_chars:
        return PageText(page, text, confidence, ratio, "blank", "no text on page")
    reasons = []
    if confidence is not None and confidence < cfg.min_page_confidence:
        reasons.append(f"OCR confidence {confidence:.0f} < {cfg.min_page_confidence:g}")
    if ratio < cfg.min_word_ratio:
        reasons.append(f"word ratio {ratio:.2f} < {cfg.min_word_ratio:g}")
    if reasons:
        return PageText(page, text, confidence, ratio, "flagged", "; ".join(reasons))
    return PageText(page, text, confidence, ratio, "ok", "")


def _pymupdf():
    try:
        import pymupdf  # type: ignore
    except ImportError:  # older wheels
        import fitz as pymupdf  # type: ignore
    return pymupdf


def _join_lines(lines: list[str]) -> str:
    out = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if out.endswith("-") and line[:1].islower():
            out = out[:-1] + line  # de-hyphenate "infec- / tion"
        else:
            out = f"{out} {line}" if out else line
    return out


def page_paragraphs(page) -> list[str]:
    """Paragraphs of one PyMuPDF page, in text-layer (reading) order.

    OCRmyPDF's text layer holds one block per line, so paragraphs are rebuilt from line
    geometry: a new paragraph starts after a vertical gap clearly wider than the gaps
    between lines of a paragraph,
    when the text jumps back up (next column), or after a short line that ends a
    sentence.
    """
    lines = []  # (x0, y0, x1, y1, text)
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"]).strip()
            if text:
                x0, y0, x1, y1 = line["bbox"]
                lines.append((x0, y0, x1, y1, text))
    if not lines:
        return []
    heights = sorted(l[3] - l[1] for l in lines)
    h = heights[len(heights) // 2] or 1.0
    widest = max(l[2] - l[0] for l in lines) or 1.0
    gaps = sorted(max(0.0, b[1] - a[3]) for a, b in zip(lines, lines[1:]) if b[1] >= a[1])
    line_gap = gaps[len(gaps) // 4] if gaps else h  # the tightest quarter: gaps inside paragraphs
    threshold = max(1.8 * line_gap, line_gap + 0.4 * h)
    paragraphs: list[list[str]] = [[lines[0][4]]]
    for prev, cur in zip(lines, lines[1:]):
        gap = cur[1] - prev[3]
        new_column = cur[1] < prev[1] - h
        short_end = (prev[2] - prev[0]) < 0.8 * widest and prev[4].rstrip()[-1:] in ".:?!"
        if gap > threshold or new_column or short_end:
            paragraphs.append([])
        paragraphs[-1].append(cur[4])
    return [p for p in (_join_lines(ls) for ls in paragraphs) if p]


def extract_text_layer(pdf_path: Path) -> list[str]:
    """Text of every page, in the order the text layer holds it, one paragraph per
    blank-line-separated block."""
    pymupdf = _pymupdf()
    with pymupdf.open(str(pdf_path)) as doc:
        return ["\n\n".join(page_paragraphs(page)) for page in doc]


def tesseract_confidence(image_png: bytes, language: str = "eng") -> Optional[float]:
    """Mean word confidence (0–100) Tesseract reports for one page image."""
    exe = shutil.which("tesseract")
    if exe is None:
        return None
    proc = subprocess.run(
        [exe, "stdin", "stdout", "-l", language, "tsv"],
        input=image_png, capture_output=True, timeout=120, check=False,
    )
    if proc.returncode != 0:
        return None
    rows = csv.DictReader(io.StringIO(proc.stdout.decode("utf-8", "replace")), delimiter="\t",
                          quoting=csv.QUOTE_NONE)
    confs = []
    for row in rows:
        try:
            conf = float(row.get("conf", "-1"))
        except ValueError:
            continue
        if conf >= 0 and (row.get("text") or "").strip():
            confs.append(conf)
    return sum(confs) / len(confs) if confs else 0.0


def page_confidences(pdf_path: Path, cfg: OcrConfig) -> list[Optional[float]]:
    pymupdf = _pymupdf()
    out: list[Optional[float]] = []
    with pymupdf.open(str(pdf_path)) as doc:
        for page in doc:
            png = page.get_pixmap(dpi=cfg.confidence_dpi, colorspace=pymupdf.csGRAY).tobytes("png")
            out.append(tesseract_confidence(png, cfg.language))
    return out


class TextLayerEngine:
    """PyMuPDF only: reads an existing text layer, no OCR. For born-digital PDFs, and
    for environments without Tesseract. Pages get no confidence, only the word ratio."""

    name = "text_layer"

    def __init__(self, cfg: OcrConfig = OcrConfig()) -> None:
        self.cfg = cfg

    def extract(self, pdf_path: Path) -> list[PageText]:
        return [assess_page(i, t, None, self.cfg) for i, t in enumerate(extract_text_layer(pdf_path), start=1)]


class OcrMyPdfEngine:
    """OCRmyPDF (Tesseract): deskew, OCR every page, write the text layer; then PyMuPDF
    extracts it and a Tesseract pass over the deskewed pages gives confidences.

    ``keep_output`` (a directory) keeps the OCRed PDF, which is what the internal viewer
    should show, since its text layer is what the chunks' positions refer to.
    """

    name = "ocrmypdf"

    def __init__(self, cfg: OcrConfig = OcrConfig(), keep_output: Optional[Path] = None) -> None:
        self.cfg = cfg
        self.keep_output = keep_output

    @staticmethod
    def available() -> bool:
        try:
            import ocrmypdf  # noqa: F401
        except Exception:  # noqa: BLE001 - broken installs raise ImportError subclasses or worse
            return False
        return shutil.which("tesseract") is not None

    def ocr_pdf(self, pdf_path: Path, out_path: Path) -> None:
        import ocrmypdf  # type: ignore

        ocrmypdf.ocr(
            str(pdf_path), str(out_path),
            language=self.cfg.language,
            deskew=self.cfg.deskew,
            rotate_pages=self.cfg.rotate_pages,
            force_ocr=True,  # scans: replace whatever text layer a scanner wrote
            output_type="pdf",
            optimize=0,
            progress_bar=False,
        )

    def extract(self, pdf_path: Path) -> list[PageText]:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "ocr.pdf"
            self.ocr_pdf(Path(pdf_path), out)
            texts = extract_text_layer(out)
            confs = page_confidences(out, self.cfg)
            if self.keep_output is not None:
                self.keep_output.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(out, self.keep_output / Path(pdf_path).name)
        return [assess_page(i, t, c, self.cfg) for i, (t, c) in enumerate(zip(texts, confs), start=1)]


class StaticOcrEngine:
    """Returns pre-set pages (tests, and re-indexing pages a reviewer approved)."""

    name = "static"

    def __init__(self, pages_by_file: dict[str, Sequence[PageText]]) -> None:
        self.pages_by_file = pages_by_file

    def extract(self, pdf_path: Path) -> list[PageText]:
        return list(self.pages_by_file[Path(pdf_path).name])


def approve(page: PageText) -> PageText:
    """A reviewer checked a flagged page: it may now be indexed."""
    return replace(page, status="ok", reason=f"approved after review ({page.reason})" if page.reason else "approved")


def default_engine(cfg: OcrConfig = OcrConfig()) -> OcrEngine:
    if cfg.engine == "ocrmypdf":
        if not OcrMyPdfEngine.available():
            raise RuntimeError("OCRmyPDF and Tesseract are required for the library OCR step "
                               "(pip install ocrmypdf; apt-get install tesseract-ocr ghostscript)")
        return OcrMyPdfEngine(cfg)
    if cfg.engine == "text_layer":
        return TextLayerEngine(cfg)
    raise ValueError(f"unknown OCR engine {cfg.engine!r}")
