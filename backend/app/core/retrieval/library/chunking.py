"""Chunking (§6 "Building the library" step 4).

Split by paragraph into chunks of about 400 tokens with about 50 tokens of overlap. Every
chunk keeps its page number and its position in the document; a chunk never spans two
pages, so ``lib_<document_id>_p<page>`` always points at the page that holds the passage.
Reference lists are skipped.

Token counts are approximate: words and punctuation marks, the unit a WordPiece
tokenizer such as MedCPT's splits into at minimum. Biomedical words often split further,
so a 400-"token" chunk can be somewhat longer for the encoder, which truncates at
``embedding.max_document_tokens`` (512).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from app.core.retrieval.library.config import ChunkingConfig

_TOKEN = re.compile(r"\w+|[^\w\s]")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])")

# Headings that open a reference list, and ones that end it.
_REF_HEADING = re.compile(
    r"^\s*(?:\d+\.?\s*)?(?:references(?: and notes)?|bibliography|literature cited|works cited|"
    r"reference list|cited literature)\s*:?\s*$", re.I)
_AFTER_REFS = re.compile(
    r"^\s*(?:\d+\.?\s*)?(?:appendix|appendices|supplementary (?:material|data|information)|"
    r"(?:table|figure|fig\.)\s+\d+)\b", re.I)
# One reference entry: "[12] Smith J, …", "12. Smith JA, Brown K. … 2001;12:33-41."
_REF_ENTRY = re.compile(
    r"^\s*(?:\[\d{1,3}\]|\d{1,3}\.)\s+[A-Z][\w'’\-]+(?:\s[A-Z]{1,3})?[,.]")
_YEAR_VOL = re.compile(r"\b(1[89]|20)\d{2}\s*[;:,.]\s*\d*|\bdoi:|et al\.", re.I)


def count_tokens(text: str) -> int:
    return len(_TOKEN.findall(text))


@dataclass(frozen=True)
class Chunk:
    page: int
    position: int  # 0-based order within the document
    text: str
    token_count: int


def looks_like_reference(paragraph: str) -> bool:
    """A paragraph that is one or more bibliography entries."""
    lines = [l for l in re.split(r"\n+", paragraph) if l.strip()]
    if not lines:
        return False
    hits = sum(1 for l in lines if _REF_ENTRY.match(l) and _YEAR_VOL.search(l))
    return hits / len(lines) >= 0.5


def paragraphs(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _pieces(paragraph: str, limit: int, counter: Callable[[str], int]) -> list[str]:
    """A paragraph longer than ``limit`` tokens, split at sentences, then words."""
    if counter(paragraph) <= limit:
        return [paragraph]
    out: list[str] = []
    for sentence in _SENTENCE.split(paragraph):
        if counter(sentence) <= limit:
            out.append(sentence)
            continue
        words = sentence.split()
        cur: list[str] = []
        for w in words:
            if cur and counter(" ".join(cur + [w])) > limit:
                out.append(" ".join(cur))
                cur = []
            cur.append(w)
        if cur:
            out.append(" ".join(cur))
    return out


def _tail(text: str, tokens: int, counter: Callable[[str], int]) -> str:
    """The last ~``tokens`` tokens of ``text``, cut at a word boundary."""
    if tokens <= 0:
        return ""
    words = text.split()
    out: list[str] = []
    for w in reversed(words):
        if counter(" ".join([w] + out)) > tokens:
            break
        out.insert(0, w)
    return " ".join(out)


def chunk_page(
    text_paragraphs: Sequence[str],
    cfg: ChunkingConfig,
    counter: Callable[[str], int] = count_tokens,
) -> list[str]:
    """Pack paragraphs into ~target-token chunks, each starting with ~overlap tokens of
    the one before it."""
    target, overlap = cfg.target_tokens, cfg.overlap_tokens
    units: list[str] = []
    for p in text_paragraphs:
        units.extend(_pieces(p, target - overlap, counter))
    chunks: list[str] = []
    cur: list[str] = []
    cur_tokens = 0
    for u in units:
        n = counter(u)
        if cur and cur_tokens + n > target:
            chunks.append(" ".join(cur))
            carry = _tail(chunks[-1], overlap, counter)
            cur, cur_tokens = ([carry], counter(carry)) if carry else ([], 0)
        cur.append(u)
        cur_tokens += n
    if cur and (not chunks or cur_tokens > counter(_tail(chunks[-1], overlap, counter))):
        chunks.append(" ".join(cur))
    return chunks


def chunk_document(
    pages: Iterable[tuple[int, str]],
    cfg: ChunkingConfig = ChunkingConfig(),
    counter: Callable[[str], int] = count_tokens,
) -> list[Chunk]:
    """Chunks for a document's indexable pages, given as ``(page_number, text)``.

    Once a reference-list heading is seen, everything after it is skipped until a
    heading that ends it (appendix, supplementary material, tables). Stray reference
    entries elsewhere are skipped too.
    """
    out: list[Chunk] = []
    in_refs = False
    position = 0
    for page_no, text in pages:
        keep: list[str] = []
        for p in paragraphs(text):
            if _REF_HEADING.match(p):
                in_refs = True
                continue
            if in_refs and _AFTER_REFS.match(p):
                in_refs = False
            if in_refs or looks_like_reference(p):
                continue
            keep.append(p)
        for c in chunk_page(keep, cfg, counter):
            out.append(Chunk(page=page_no, position=position, text=c, token_count=counter(c)))
            position += 1
    return out
