"""Where the library lives (§6 "Building the library" step 6; §17 tables).

``PgLibraryStore`` is the real one: pgvector in the existing Supabase Postgres, tables
``library_documents`` and ``library_chunks`` (migration 0006), an HNSW index on cosine
distance and a generated ``tsvector`` column with a GIN index for full-text search.
``InMemoryLibraryStore`` has the same behaviour (cosine similarity, BM25 full-text) for
tests and local runs.

Neither store decides anything: dedup, flagging and ranking live in ``ingest`` and
``search``.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Iterable, Literal, Optional, Protocol, Sequence

DocumentStatus = Literal["indexed", "needs_review", "linked_pubmed", "failed"]
SEARCHABLE_STATUSES = ("indexed", "needs_review")  # needs_review: some pages still held back


@dataclass(frozen=True)
class LibraryDocument:
    document_id: str
    title: str
    sha256: str
    authors: tuple[str, ...] = ()
    year: Optional[int] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    study_type: Optional[str] = None  # StudyType value from the manifest; None = unknown
    storage_key: Optional[str] = None
    status: DocumentStatus = "indexed"
    linked_pmid: Optional[str] = None  # set when PubMed already covers this paper
    ocr_engine: str = ""
    # {"pages": {"<n>": {"status", "confidence", "word_ratio", "reason"}},
    #  "flagged_pages": [...], "held_text": {"<n>": "<text awaiting review>"}}
    ocr_quality: dict = field(default_factory=dict)
    uploaded_by: Optional[str] = None
    ingested_at: Optional[datetime] = None


@dataclass(frozen=True)
class StoredChunk:
    chunk_id: str
    document_id: str
    page: int
    position: int
    text: str
    token_count: int
    embedding: tuple[float, ...]
    embedding_model: str
    embedding_version: str


@dataclass(frozen=True)
class ChunkHit:
    chunk: StoredChunk
    document: LibraryDocument
    score: float


class LibraryStore(Protocol):
    def get_document(self, document_id: str) -> Optional[LibraryDocument]: ...
    def find_by_sha256(self, sha256: str) -> Optional[LibraryDocument]: ...
    def find_by_identifier(self, doi: Optional[str], pmid: Optional[str]) -> Optional[LibraryDocument]: ...
    def save_document(self, doc: LibraryDocument) -> None: ...
    def add_chunks(self, chunks: Sequence[StoredChunk]) -> None: ...
    def chunks_for(self, document_id: str) -> list[StoredChunk]: ...
    def vector_search(self, vector: Sequence[float], *, model: str, version: str, n: int) -> list[ChunkHit]: ...
    def text_search(self, query: str, *, n: int) -> list[ChunkHit]: ...


# ------------------------------------------------------------------ in memory

_STOP = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the this to was were "
    "will with does do did can could may might not no than then there these those which who whom".split()
)
_WORD = re.compile(r"[a-z0-9]+")


def _terms(text: str) -> list[str]:
    out = []
    for w in _WORD.findall(text.lower()):
        if w in _STOP or len(w) < 2:
            continue
        for suf in ("ies", "es", "s", "ing", "ed"):
            if w.endswith(suf) and len(w) - len(suf) >= 3:
                w = w[: -len(suf)]
                break
        out.append(w)
    return out


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class InMemoryLibraryStore:
    def __init__(self) -> None:
        self.documents: dict[str, LibraryDocument] = {}
        self.chunks: dict[str, StoredChunk] = {}

    def get_document(self, document_id: str) -> Optional[LibraryDocument]:
        return self.documents.get(document_id)

    def find_by_sha256(self, sha256: str) -> Optional[LibraryDocument]:
        return next((d for d in self.documents.values() if d.sha256 == sha256), None)

    def find_by_identifier(self, doi: Optional[str], pmid: Optional[str]) -> Optional[LibraryDocument]:
        for d in self.documents.values():
            if (doi and d.doi == doi) or (pmid and d.pmid == pmid):
                return d
        return None

    def save_document(self, doc: LibraryDocument) -> None:
        self.documents[doc.document_id] = doc

    def add_chunks(self, chunks: Sequence[StoredChunk]) -> None:
        for c in chunks:
            if c.document_id not in self.documents:
                raise KeyError(f"unknown document {c.document_id}")
            self.chunks[c.chunk_id] = c

    def chunks_for(self, document_id: str) -> list[StoredChunk]:
        return sorted((c for c in self.chunks.values() if c.document_id == document_id), key=lambda c: c.position)

    def _searchable(self) -> Iterable[tuple[StoredChunk, LibraryDocument]]:
        for c in self.chunks.values():
            d = self.documents[c.document_id]
            if d.status in SEARCHABLE_STATUSES:
                yield c, d

    def vector_search(self, vector: Sequence[float], *, model: str, version: str, n: int) -> list[ChunkHit]:
        hits = [
            ChunkHit(c, d, _cosine(vector, c.embedding))
            for c, d in self._searchable()
            if c.embedding_model == model and c.embedding_version == version
        ]
        hits.sort(key=lambda h: (-h.score, h.chunk.chunk_id))
        return hits[:n]

    def text_search(self, query: str, *, n: int) -> list[ChunkHit]:
        """BM25 (k1=1.2, b=0.75) over stemmed words; any query word may match."""
        q = set(_terms(query))
        items = list(self._searchable())
        if not q or not items:
            return []
        docs = [(c, d, Counter(_terms(c.text))) for c, d in items]
        avg = sum(sum(tf.values()) for _, _, tf in docs) / len(docs) or 1.0
        df = Counter(t for _, _, tf in docs for t in set(tf) if t in q)
        N = len(docs)
        hits = []
        for c, d, tf in docs:
            length = sum(tf.values())
            score = 0.0
            for t in q:
                if tf[t]:
                    idf = math.log(1 + (N - df[t] + 0.5) / (df[t] + 0.5))
                    score += idf * tf[t] * 2.2 / (tf[t] + 1.2 * (0.25 + 0.75 * length / avg))
            if score > 0:
                hits.append(ChunkHit(c, d, score))
        hits.sort(key=lambda h: (-h.score, h.chunk.chunk_id))
        return hits[:n]


# ------------------------------------------------------------------ Postgres


def vector_literal(v: Sequence[float]) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in v) + "]"


def _parse_vector(v: Any) -> tuple[float, ...]:
    if v is None:
        return ()
    if isinstance(v, str):
        return tuple(float(x) for x in v.strip("[]").split(",") if x)
    return tuple(float(x) for x in v)


_DOC_COLS = ("id, title, authors, year, doi, pmid, study_type, storage_key, sha256, status, "
             "linked_pmid, ocr_engine, ocr_quality, uploaded_by, ingested_at")
_CHUNK_COLS = ("c.id, c.document_id, c.page, c.position, c.text, c.token_count, c.embedding::text, "
               "c.embedding_model, c.embedding_version")


VECTOR_SEARCH_SQL = (
    "SELECT {cols}, 1 - c.dist AS score FROM ("
    "  SELECT ic.*, ic.embedding <=> CAST(:q AS vector) AS dist FROM library_chunks ic"
    "  ORDER BY ic.embedding <=> CAST(:q AS vector) LIMIT :over"
    ") c JOIN library_documents d ON d.id = c.document_id "
    "WHERE c.embedding_model = :m AND c.embedding_version = :v AND d.status IN ('indexed', 'needs_review') "
    "ORDER BY c.dist, c.id LIMIT :n"
)


class PgLibraryStore:
    """pgvector-backed store. ``engine`` is a synchronous SQLAlchemy engine on the app's
    Postgres (``DATABASE_URL_SYNC``); the tables come from Alembic migration 0006."""

    def __init__(self, engine) -> None:
        self.engine = engine

    @staticmethod
    def _doc(row) -> LibraryDocument:
        quality = row[12]
        if isinstance(quality, str):
            quality = json.loads(quality)
        authors = row[2]
        if isinstance(authors, str):
            authors = json.loads(authors)
        return LibraryDocument(
            document_id=row[0], title=row[1], authors=tuple(authors or ()), year=row[3], doi=row[4],
            pmid=row[5], study_type=row[6], storage_key=row[7], sha256=row[8], status=row[9],
            linked_pmid=row[10], ocr_engine=row[11] or "", ocr_quality=quality or {},
            uploaded_by=row[13], ingested_at=row[14],
        )

    @staticmethod
    def _chunk(row) -> StoredChunk:
        return StoredChunk(
            chunk_id=row[0], document_id=row[1], page=row[2], position=row[3], text=row[4],
            token_count=row[5], embedding=_parse_vector(row[6]), embedding_model=row[7],
            embedding_version=row[8],
        )

    def _one_doc(self, where: str, params: dict) -> Optional[LibraryDocument]:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            row = conn.execute(text(f"SELECT {_DOC_COLS} FROM library_documents WHERE {where} LIMIT 1"), params).first()
        return self._doc(row) if row else None

    def get_document(self, document_id: str) -> Optional[LibraryDocument]:
        return self._one_doc("id = :id", {"id": document_id})

    def find_by_sha256(self, sha256: str) -> Optional[LibraryDocument]:
        return self._one_doc("sha256 = :s", {"s": sha256})

    def find_by_identifier(self, doi: Optional[str], pmid: Optional[str]) -> Optional[LibraryDocument]:
        if not doi and not pmid:
            return None
        return self._one_doc("(doi = :doi) OR (pmid = :pmid)", {"doi": doi or "\x00", "pmid": pmid or "\x00"})

    def save_document(self, doc: LibraryDocument) -> None:
        from sqlalchemy import text

        params = {
            "id": doc.document_id, "title": doc.title, "authors": json.dumps(list(doc.authors)),
            "year": doc.year, "doi": doc.doi, "pmid": doc.pmid, "study_type": doc.study_type,
            "storage_key": doc.storage_key, "sha256": doc.sha256, "status": doc.status,
            "linked_pmid": doc.linked_pmid, "ocr_engine": doc.ocr_engine,
            "ocr_quality": json.dumps(doc.ocr_quality), "uploaded_by": doc.uploaded_by,
            "ingested_at": doc.ingested_at or datetime.now(timezone.utc),
        }
        sql = text(
            "INSERT INTO library_documents (id, title, authors, year, doi, pmid, study_type, storage_key, "
            "sha256, status, linked_pmid, ocr_engine, ocr_quality, uploaded_by, ingested_at) VALUES "
            "(:id, :title, CAST(:authors AS jsonb), :year, :doi, :pmid, :study_type, :storage_key, :sha256, "
            ":status, :linked_pmid, :ocr_engine, CAST(:ocr_quality AS jsonb), :uploaded_by, :ingested_at) "
            "ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title, authors = EXCLUDED.authors, "
            "year = EXCLUDED.year, doi = EXCLUDED.doi, pmid = EXCLUDED.pmid, study_type = EXCLUDED.study_type, "
            "storage_key = EXCLUDED.storage_key, status = EXCLUDED.status, linked_pmid = EXCLUDED.linked_pmid, "
            "ocr_engine = EXCLUDED.ocr_engine, ocr_quality = EXCLUDED.ocr_quality, "
            "uploaded_by = EXCLUDED.uploaded_by"
        )
        with self.engine.begin() as conn:
            conn.execute(sql, params)

    def add_chunks(self, chunks: Sequence[StoredChunk]) -> None:
        from sqlalchemy import text

        if not chunks:
            return
        sql = text(
            "INSERT INTO library_chunks (id, document_id, page, position, text, token_count, embedding, "
            "embedding_model, embedding_version) VALUES (:id, :document_id, :page, :position, :text, "
            ":token_count, CAST(:embedding AS vector), :embedding_model, :embedding_version) "
            "ON CONFLICT (id) DO UPDATE SET text = EXCLUDED.text, token_count = EXCLUDED.token_count, "
            "embedding = EXCLUDED.embedding, embedding_model = EXCLUDED.embedding_model, "
            "embedding_version = EXCLUDED.embedding_version"
        )
        rows = [
            {"id": c.chunk_id, "document_id": c.document_id, "page": c.page, "position": c.position,
             "text": c.text, "token_count": c.token_count, "embedding": vector_literal(c.embedding),
             "embedding_model": c.embedding_model, "embedding_version": c.embedding_version}
            for c in chunks
        ]
        with self.engine.begin() as conn:
            conn.execute(sql, rows)

    def chunks_for(self, document_id: str) -> list[StoredChunk]:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT {_CHUNK_COLS} FROM library_chunks c WHERE c.document_id = :d ORDER BY c.position"),
                {"d": document_id},
            ).all()
        return [self._chunk(r) for r in rows]

    def _hits(self, sql: str, params: dict) -> list[ChunkHit]:
        from sqlalchemy import text

        doc_cols = ", ".join(f"d.{c.strip()}" for c in _DOC_COLS.split(","))
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql.format(cols=f"{_CHUNK_COLS}, {doc_cols}")), params).all()
        return [ChunkHit(self._chunk(r[:9]), self._doc(r[9:24]), float(r[24])) for r in rows]

    def vector_search(self, vector: Sequence[float], *, model: str, version: str, n: int) -> list[ChunkHit]:
        # The inner query is a bare ORDER BY cosine distance (<=>) with a LIMIT, the shape
        # the HNSW index (vector_cosine_ops) serves; filters on a join would make Postgres
        # skip the index. It over-fetches (×4) so that filtering out other embedding
        # models and held-back documents still leaves n, and ef_search is raised to match.
        # Score = 1 - cosine distance.
        from sqlalchemy import text

        over = max(n * 4, 40)
        sql = VECTOR_SEARCH_SQL
        params = {"q": vector_literal(vector), "m": model, "v": version, "n": n, "over": over}
        doc_cols = ", ".join(f"d.{c.strip()}" for c in _DOC_COLS.split(","))
        with self.engine.begin() as conn:
            conn.execute(text(f"SET LOCAL hnsw.ef_search = {int(min(over, 1000))}"))
            rows = conn.execute(text(sql.format(cols=f"{_CHUNK_COLS}, {doc_cols}")), params).all()
        return [ChunkHit(self._chunk(r[:9]), self._doc(r[9:24]), float(r[24])) for r in rows]

    def text_search(self, query: str, *, n: int) -> list[ChunkHit]:
        # plainto_tsquery ANDs every word; turn it into an OR so a chunk that names the
        # drug but not the outcome still ranks (ts_rank_cd rewards matching more words).
        sql = (
            "WITH q AS (SELECT NULLIF(replace(plainto_tsquery('english', :q)::text, ' & ', ' | '), '') AS t) "
            "SELECT {cols}, ts_rank_cd(c.tsv, to_tsquery('english', q.t)) AS score "
            "FROM q, library_chunks c JOIN library_documents d ON d.id = c.document_id "
            "WHERE q.t IS NOT NULL AND c.tsv @@ to_tsquery('english', q.t) "
            "AND d.status IN ('indexed', 'needs_review') "
            "ORDER BY score DESC, c.id LIMIT :n"
        )
        return self._hits(sql, {"q": query, "n": n})
