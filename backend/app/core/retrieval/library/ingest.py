"""Building the library: an offline batch job, separate from video processing (§6).

For each PDF listed in the manifest:

1. **SHA-256** of the file: the same scan uploaded twice is caught before any OCR.
2. **PubMed dedup**: a document with a PMID, or a DOI PubMed knows, is *linked* to that
   PubMed record (``status = linked_pubmed``, ``linked_pmid``) and not indexed, because
   PubMed stays the primary source. A second scan with the DOI or PMID of a document
   already in the library is reported as a duplicate.
3. **OCR** (``ocr.OcrEngine``). Pages with low OCR confidence are flagged and held back
   (their text is kept in ``ocr_quality.held_text`` for the reviewer) until someone
   approves them with ``approve_pages``; the document is ``needs_review`` meanwhile and
   its other pages are searchable.
4. **Chunk** by paragraph (~400 tokens, ~50 overlap), skipping reference lists.
5. **Embed** each chunk with the configured document encoder and record the model and
   version on the chunk.
6. **Store** the document and its chunks.

Failures are per document: one bad scan never stops the batch.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional, Protocol, Sequence

from app.core.retrieval.library.chunking import Chunk, chunk_document
from app.core.retrieval.library.config import LibraryConfig
from app.core.retrieval.library.embeddings import Embedder
from app.core.retrieval.library.manifest import ManifestEntry, ManifestError, parse_manifest
from app.core.retrieval.library.ocr import OcrEngine, PageText
from app.core.retrieval.library.store import LibraryDocument, LibraryStore, StoredChunk

log = logging.getLogger(__name__)

Outcome = Literal[
    "indexed", "needs_review", "linked_pubmed", "duplicate_file", "duplicate_identifier",
    "missing_file", "failed",
]


class PubMedLookup(Protocol):
    """Does PubMed already hold this paper? Returns its PMID, or None."""

    def pmid_for_doi(self, doi: str) -> Optional[str]: ...


class PubMedDoiLookup:
    """``PubMedLookup`` over the retrieval package's PubMed client (ESearch on ``[doi]``)."""

    def __init__(self, client) -> None:
        self.client = client

    def pmid_for_doi(self, doi: str) -> Optional[str]:
        pmids = self.client.search(f"{doi}[doi]", max_results=2)
        return pmids[0] if len(pmids) == 1 else None


@dataclass(frozen=True)
class IngestOutcome:
    file: str
    outcome: Outcome
    document_id: Optional[str] = None
    chunks: int = 0
    flagged_pages: tuple[int, ...] = ()
    linked_pmid: Optional[str] = None
    message: str = ""


@dataclass
class IngestReport:
    outcomes: list[IngestOutcome] = field(default_factory=list)
    manifest_errors: list[ManifestError] = field(default_factory=list)

    def count(self, outcome: Outcome) -> int:
        return sum(1 for o in self.outcomes if o.outcome == outcome)

    def summary(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for o in self.outcomes:
            out[o.outcome] = out.get(o.outcome, 0) + 1
        out["manifest_errors"] = len([e for e in self.manifest_errors if e.row > 0])
        return out


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def document_id_for(sha256: str) -> str:
    """Stable ID from the file hash: the same scan always gets the same ID."""
    return sha256[:16]


def chunk_id_for(document_id: str, position: int) -> str:
    return f"{document_id}_{position:05d}"


def _page_quality(pages: Sequence[PageText]) -> dict:
    return {
        "pages": {
            str(p.page): {
                "status": p.status,
                "confidence": None if p.confidence is None else round(p.confidence, 1),
                "word_ratio": round(p.word_ratio, 3),
                "reason": p.reason,
            }
            for p in pages
        },
        "flagged_pages": [p.page for p in pages if p.status == "flagged"],
        "held_text": {str(p.page): p.text for p in pages if p.status == "flagged"},
    }


class LibraryIngestor:
    def __init__(
        self,
        store: LibraryStore,
        ocr: OcrEngine,
        embedder: Embedder,
        config: LibraryConfig = LibraryConfig(),
        pubmed: Optional[PubMedLookup] = None,
    ) -> None:
        self.store = store
        self.ocr = ocr
        self.embedder = embedder
        self.config = config
        self.pubmed = pubmed

    # ---------------------------------------------------------------- batch

    def ingest_batch(self, manifest, pdf_dir: Path, *, uploaded_by: Optional[str] = None,
                     storage_prefix: str = "library/") -> IngestReport:
        entries, errors = parse_manifest(manifest)
        report = IngestReport(manifest_errors=list(errors))
        listed = {e.file for e in entries}
        for e in entries:
            report.outcomes.append(
                self.ingest_file(e, Path(pdf_dir) / e.file, uploaded_by=uploaded_by,
                                 storage_key=f"{storage_prefix}{e.file}")
            )
        for pdf in sorted(Path(pdf_dir).glob("*.pdf")):
            if pdf.name not in listed:
                report.manifest_errors.append(ManifestError(0, f"{pdf.name} is not in the manifest; not ingested"))
        return report

    # ---------------------------------------------------------------- one file

    def ingest_file(self, entry: ManifestEntry, pdf_path: Path, *, uploaded_by: Optional[str] = None,
                    storage_key: Optional[str] = None) -> IngestOutcome:
        if not pdf_path.is_file():
            return IngestOutcome(entry.file, "missing_file", message="file listed in the manifest was not uploaded")
        try:
            return self._ingest(entry, pdf_path, uploaded_by, storage_key)
        except Exception as exc:  # noqa: BLE001 - one bad scan never stops the batch
            log.exception("library ingest failed for %s", entry.file)
            return IngestOutcome(entry.file, "failed", message=f"{type(exc).__name__}: {exc}"[:500])

    def _ingest(self, entry: ManifestEntry, pdf_path: Path, uploaded_by, storage_key) -> IngestOutcome:
        sha = sha256_file(pdf_path)
        existing = self.store.find_by_sha256(sha)
        if existing is not None:
            return IngestOutcome(entry.file, "duplicate_file", existing.document_id,
                                 message=f"same file as document {existing.document_id} ({existing.title!r})")
        doc_id = document_id_for(sha)
        base = LibraryDocument(
            document_id=doc_id, title=entry.title, sha256=sha, authors=entry.authors, year=entry.year,
            doi=entry.doi, pmid=entry.pmid, study_type=entry.study_type, storage_key=storage_key,
            uploaded_by=uploaded_by, ingested_at=datetime.now(timezone.utc), ocr_engine=self.ocr.name,
        )

        same = self.store.find_by_identifier(entry.doi, entry.pmid)
        if same is not None:
            return IngestOutcome(entry.file, "duplicate_identifier", same.document_id,
                                 message=f"DOI/PMID already in the library as document {same.document_id}")

        linked, note = self._pubmed_link(entry)
        if linked:
            self.store.save_document(replace(base, status="linked_pubmed", linked_pmid=linked, ocr_engine=""))
            return IngestOutcome(entry.file, "linked_pubmed", doc_id, linked_pmid=linked,
                                 message="PubMed already covers this paper; linked, not indexed")

        pages = self.ocr.extract(pdf_path)
        readable = [p for p in pages if p.status != "blank"]
        if not readable:
            return IngestOutcome(entry.file, "failed", doc_id, message="no text found on any page")
        ok = [p for p in pages if p.status == "ok"]
        flagged = tuple(p.page for p in pages if p.status == "flagged")
        quality = _page_quality(pages)
        if note:
            quality["pubmed_check"] = note
        status = "needs_review" if flagged else "indexed"
        doc = replace(base, status=status, ocr_quality=quality)
        stored = self._embed(doc, chunk_document([(p.page, p.text) for p in ok], self.config.chunking))
        self.store.save_document(doc)
        self.store.add_chunks(stored)
        msg = f"{len(flagged)} page(s) held for OCR review" if flagged else ""
        if note:
            msg = "; ".join(filter(None, [msg, note]))
        return IngestOutcome(entry.file, status, doc_id, chunks=len(stored), flagged_pages=flagged, message=msg)

    def _pubmed_link(self, entry: ManifestEntry) -> tuple[Optional[str], str]:
        if entry.pmid:
            return entry.pmid, ""  # a PMID is a PubMed record by definition
        if entry.doi and self.pubmed is not None:
            try:
                return self.pubmed.pmid_for_doi(entry.doi), ""
            except Exception as exc:  # noqa: BLE001 - PubMed down must not block the library
                return None, f"PubMed DOI check failed ({type(exc).__name__}); indexed anyway"
        return None, ""

    def _embed(self, doc: LibraryDocument, chunks: Sequence[Chunk], start: int = 0) -> list[StoredChunk]:
        if not chunks:
            return []
        vectors = self.embedder.embed_documents([(doc.title, c.text) for c in chunks])
        if len(vectors) != len(chunks):
            raise ValueError(f"embedder returned {len(vectors)} vectors for {len(chunks)} chunks")
        return [
            StoredChunk(
                chunk_id=chunk_id_for(doc.document_id, start + c.position), document_id=doc.document_id,
                page=c.page, position=start + c.position, text=c.text, token_count=c.token_count,
                embedding=tuple(v), embedding_model=self.embedder.model_name,
                embedding_version=self.embedder.model_version,
            )
            for c, v in zip(chunks, vectors)
        ]

    # ---------------------------------------------------------------- review

    def approve_pages(self, document_id: str, pages: Sequence[int], *, reviewer: str,
                      corrected_text: Optional[dict[int, str]] = None) -> IngestOutcome:
        """A person checked flagged pages: index them (optionally with corrected text)."""
        doc = self.store.get_document(document_id)
        if doc is None:
            raise KeyError(f"unknown library document {document_id}")
        quality = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
                   for k, v in doc.ocr_quality.items()}
        held: dict = quality.get("held_text", {})
        flagged = list(quality.get("flagged_pages", []))
        unknown = [p for p in pages if p not in flagged]
        if unknown:
            raise ValueError(f"pages {unknown} are not awaiting review")
        corrected_text = corrected_text or {}
        texts = [(p, corrected_text.get(p, held[str(p)])) for p in sorted(pages)]
        existing = self.store.chunks_for(document_id)
        start = (max(c.position for c in existing) + 1) if existing else 0
        stored = self._embed(doc, chunk_document(texts, self.config.chunking), start=start)
        for p in pages:
            flagged.remove(p)
            held.pop(str(p), None)
            page_q = quality.setdefault("pages", {}).setdefault(str(p), {})
            page_q.update(status="ok", reviewed_by=reviewer, corrected=p in corrected_text)
        quality["flagged_pages"] = flagged
        quality["held_text"] = held
        doc = replace(doc, ocr_quality=quality, status="needs_review" if flagged else "indexed")
        self.store.save_document(doc)
        self.store.add_chunks(stored)
        return IngestOutcome(doc.title, doc.status, document_id, chunks=len(stored), flagged_pages=tuple(flagged))
