"""Tesseract (via OCRmyPDF) vs EasyOCR on scanned pages: word error rate and reading
order (target design §6 "OCR": "Before committing, run Tesseract and EasyOCR on about 20
pages of the real scans and compare word error rate and reading order").

Two modes. Run from backend/:

    # Generated sample scans (what the automated build could run; no real scans)
    python scripts/compare_library_ocr.py --samples

    # Real scans: a folder of single-page PDFs, each with a hand-typed <name>.txt
    # transcript (paragraphs separated by blank lines, in reading order)
    python scripts/compare_library_ocr.py --dir path/to/pages

Word error rate: word-level edit distance / reference words, on lower-cased words with
punctuation removed. Reading order: the share of consecutive reference paragraphs whose
openings appear in the same order in the OCR text (1.0 = perfect; a two-column page read
straight across scores low). EasyOCR is skipped if it isn't installed.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.retrieval.library.config import OcrConfig  # noqa: E402
from app.core.retrieval.library.ocr import OcrMyPdfEngine  # noqa: E402


def words(s: str) -> list[str]:
    return re.sub(r"[^a-z0-9 ]", " ", s.lower()).split()


def wer(ref: str, hyp: str) -> float:
    a, b = words(ref), words(hyp)
    d = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(b) + 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (a[i - 1] != b[j - 1]))
    return d[len(b)] / max(1, len(a))


def reading_order(ref_paragraphs: list[str], hyp: str) -> float:
    h = " ".join(words(hyp))
    pos = []
    for p in ref_paragraphs:
        opening = " ".join(words(p)[:4])
        pos.append(h.find(opening) if opening else -1)
    pairs = list(zip(pos, pos[1:]))
    if not pairs:
        return 1.0
    return sum(1 for a, b in pairs if a != -1 and b != -1 and a < b) / len(pairs)


def tesseract_text(pdf: Path) -> str:
    return "\n\n".join(p.text for p in OcrMyPdfEngine(OcrConfig()).extract(pdf))


def easyocr_text(pdf: Path):
    try:
        import easyocr  # type: ignore
    except ImportError:
        return None
    import pymupdf

    reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    out = []
    with pymupdf.open(str(pdf)) as doc:
        for page in doc:
            png = page.get_pixmap(dpi=300).tobytes("png")
            out.append(" ".join(reader.readtext(png, detail=0, paragraph=True)))
    return "\n\n".join(out)


def sample_pages(tmp: Path) -> list[tuple[str, Path, list[str]]]:
    from app.tests.library_samples import GARLIC_PAGES, TWO_COLUMN_PAGE, make_scanned_pdf

    cases = []
    for name, page, kw in [
        ("garlic_p1_straight", GARLIC_PAGES[0], {}),
        ("garlic_p1_skew2", GARLIC_PAGES[0], {"skew_degrees": 2.0}),
        ("garlic_p2_noise", GARLIC_PAGES[1], {"noise": 0.002, "seed": 3}),
        ("two_column", TWO_COLUMN_PAGE, {"skew_degrees": -1.0}),
        ("garlic_p1_150dpi_blur", GARLIC_PAGES[0], {"dpi": 150, "blur": 0.8}),
    ]:
        pdf = make_scanned_pdf(tmp / f"{name}.pdf", [page], **kw)
        cases.append((name, pdf, [page.heading, *page.paragraphs] if page.heading else list(page.paragraphs)))
    return cases


def dir_pages(d: Path) -> list[tuple[str, Path, list[str]]]:
    cases = []
    for pdf in sorted(d.glob("*.pdf")):
        txt = pdf.with_suffix(".txt")
        if txt.exists():
            cases.append((pdf.stem, pdf, [p.strip() for p in txt.read_text().split("\n\n") if p.strip()]))
    return cases


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--samples", action="store_true")
    g.add_argument("--dir", type=Path)
    args = ap.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        cases = sample_pages(Path(tmp)) if args.samples else dir_pages(args.dir)
        print("| Page | Tesseract WER | Tesseract order | EasyOCR WER | EasyOCR order |")
        print("|---|---|---|---|---|")
        for name, pdf, ref in cases:
            t = tesseract_text(pdf)
            e = easyocr_text(pdf)
            ref_text = " ".join(ref)
            e_cols = ("n/a", "n/a") if e is None else (f"{wer(ref_text, e):.3f}", f"{reading_order(ref, e):.2f}")
            print(f"| {name} | {wer(ref_text, t):.3f} | {reading_order(ref, t):.2f} | {e_cols[0]} | {e_cols[1]} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
