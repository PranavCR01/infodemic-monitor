"""Generated sample "scans" for the library tests (no real scans are committed).

Each page is laid out with reportlab, rendered to a greyscale image, optionally rotated a
little (to exercise deskew) and noised, and written back into a PDF with no text layer:
the same shape as a scanner's output. Ground-truth text is returned alongside, so OCR
quality (word error rate, reading order) can be measured.
"""
from __future__ import annotations

import io
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class SamplePage:
    paragraphs: Sequence[str]
    columns: int = 1  # 1 or 2
    heading: str = ""


def _layout_pdf(pages: Sequence[SamplePage]) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import BaseDocTemplate, Frame, FrameBreak, PageTemplate, PageBreak, Paragraph, Spacer

    buf = io.BytesIO()
    w, h = letter
    margin, gap = 54, 24
    one = Frame(margin, margin, w - 2 * margin, h - 2 * margin, id="one")
    col_w = (w - 2 * margin - gap) / 2
    left = Frame(margin, margin, col_w, h - 2 * margin - 40, id="left")
    right = Frame(margin + col_w + gap, margin, col_w, h - 2 * margin - 40, id="right")
    head = Frame(margin, h - margin - 40, w - 2 * margin, 40, id="head")
    doc = BaseDocTemplate(buf, pagesize=letter)
    templates = [PageTemplate(id="one", frames=[one]), PageTemplate(id="two", frames=[head, left, right])]
    if pages and pages[0].columns == 2:
        templates.reverse()  # the first template is the first page's
    doc.addPageTemplates(templates)
    body = ParagraphStyle("body", fontName="Times-Roman", fontSize=12, leading=16, spaceAfter=10)
    title = ParagraphStyle("title", fontName="Times-Bold", fontSize=15, leading=19, spaceAfter=12)
    from reportlab.platypus.doctemplate import NextPageTemplate

    story = []
    for i, page in enumerate(pages):
        if i:
            story.append(NextPageTemplate("two" if page.columns == 2 else "one"))
            story.append(PageBreak())
        if page.columns == 2:
            story.append(Paragraph(page.heading or " ", title))
            story.append(FrameBreak())
            half = (len(page.paragraphs) + 1) // 2
            for p in page.paragraphs[:half]:
                story.append(Paragraph(p, body))
            story.append(FrameBreak())
            for p in page.paragraphs[half:]:
                story.append(Paragraph(p, body))
        else:
            if page.heading:
                story.append(Paragraph(page.heading, title))
            for p in page.paragraphs:
                story.append(Paragraph(p, body))
            story.append(Spacer(1, 1))
    doc.build(story)
    return buf.getvalue()


def make_scanned_pdf(
    path: Path,
    pages: Sequence[SamplePage],
    *,
    dpi: int = 200,
    skew_degrees: float = 0.0,
    noise: float = 0.0,
    blur: float = 0.0,
    seed: int = 0,
) -> Path:
    """Write an image-only PDF of ``pages`` to ``path``."""
    import pymupdf
    from PIL import Image, ImageFilter

    rng = random.Random(seed)
    src = pymupdf.open(stream=_layout_pdf(pages), filetype="pdf")
    out = pymupdf.open()
    for page in src:
        pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
        img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
        if skew_degrees:
            img = img.rotate(skew_degrees, resample=Image.BICUBIC, expand=False, fillcolor=255)
        if blur:
            img = img.filter(ImageFilter.GaussianBlur(blur))
        if noise:
            px = img.load()
            for _ in range(int(img.width * img.height * noise)):
                x, y = rng.randrange(img.width), rng.randrange(img.height)
                px[x, y] = 0 if px[x, y] > 128 else 255
        png = io.BytesIO()
        img.save(png, format="PNG")
        rect = page.rect
        new = out.new_page(width=rect.width, height=rect.height)
        new.insert_image(rect, stream=png.getvalue())
    path.parent.mkdir(parents=True, exist_ok=True)
    out.save(str(path))
    return path


def make_text_pdf(path: Path, pages: Sequence[SamplePage]) -> Path:
    """A born-digital PDF (real text layer, no OCR needed)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_layout_pdf(pages))
    return path


GARLIC_PAGES = [
    SamplePage(
        heading="Garlic supplementation and the common cold: a randomised trial",
        paragraphs=[
            "Background. Garlic is widely promoted as a remedy that prevents the common cold. "
            "We tested whether a daily allicin-containing garlic supplement reduces the number of colds in adults.",
            "Methods. One hundred and forty six healthy adult volunteers were randomly assigned to a garlic "
            "supplement or placebo for twelve weeks during the winter season.",
        ],
    ),
    SamplePage(
        paragraphs=[
            "Results. The garlic group reported twenty four colds compared with sixty five in the placebo group. "
            "Duration of symptoms did not differ between the two groups.",
            "Conclusions. A single small trial suggests garlic may prevent colds, but the evidence is weak and "
            "needs replication in larger trials.",
            "References",
            "1. Smith J, Brown K. Allicin and respiratory infection. J Herb Med. 2001;12:33-41.",
            "2. Jones A. Common cold epidemiology. Lancet. 1999;354:1-5.",
        ],
    ),
]

TWO_COLUMN_PAGE = SamplePage(
    heading="Fluoride exposure and childhood cognition",
    columns=2,
    paragraphs=[
        "Alpha paragraph. The left column opens with a description of the cohort of children recruited at birth.",
        "Bravo paragraph. Water fluoride concentration was measured at each household during pregnancy.",
        "Charlie paragraph. The right column reports intelligence scores measured at the age of seven years.",
        "Delta paragraph. No association between fluoride exposure and intelligence was found after adjustment.",
    ],
)
