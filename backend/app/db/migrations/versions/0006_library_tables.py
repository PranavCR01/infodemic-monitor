"""offline library: library_documents and library_chunks (pgvector)

Target design §6 "Fallback: the lab's offline library" and §17 tables. Chunks carry a
768-dimension embedding with an HNSW index on cosine distance and a generated tsvector
column with a GIN index for full-text search.

Needs the pgvector extension (enabled by default on Supabase; elsewhere install
postgresql-<ver>-pgvector). Postgres only: on other databases this migration does nothing.

These tables have no SQLAlchemy model in ``app.db.base.Base`` on purpose: ``Base`` is also
used with ``create_all`` on SQLite in tests and as a startup fallback, and SQLite has no
vector or tsvector type. The library store uses SQL directly
(``app.core.retrieval.library.store.PgLibraryStore``).

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-22

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE library_documents (
    id            varchar(64) PRIMARY KEY,
    title         text NOT NULL,
    authors       jsonb NOT NULL DEFAULT '[]'::jsonb,
    year          integer,
    doi           varchar(255),
    pmid          varchar(16),
    study_type    varchar(32),
    storage_key   text,
    sha256        char(64) NOT NULL UNIQUE,
    status        varchar(16) NOT NULL DEFAULT 'indexed'
                  CHECK (status IN ('indexed', 'needs_review', 'linked_pubmed', 'failed')),
    linked_pmid   varchar(16),
    ocr_engine    varchar(32) NOT NULL DEFAULT '',
    ocr_quality   jsonb NOT NULL DEFAULT '{}'::jsonb,
    uploaded_by   varchar(255),
    ingested_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_library_documents_doi ON library_documents (doi);
CREATE INDEX ix_library_documents_pmid ON library_documents (pmid);

CREATE TABLE library_chunks (
    id                 varchar(96) PRIMARY KEY,
    document_id        varchar(64) NOT NULL REFERENCES library_documents (id) ON DELETE CASCADE,
    page               integer NOT NULL CHECK (page >= 1),
    position           integer NOT NULL CHECK (position >= 0),
    text               text NOT NULL,
    token_count        integer NOT NULL,
    embedding          vector(768) NOT NULL,
    embedding_model    varchar(255) NOT NULL,
    embedding_version  varchar(64) NOT NULL,
    tsv                tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
    created_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, position)
);
CREATE INDEX ix_library_chunks_document_page ON library_chunks (document_id, page);
CREATE INDEX ix_library_chunks_embedding_hnsw ON library_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ix_library_chunks_tsv ON library_chunks USING gin (tsv);
"""

DOWNGRADE_SQL = """
DROP TABLE IF EXISTS library_chunks;
DROP TABLE IF EXISTS library_documents;
"""


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return
    for stmt in filter(None, (s.strip() for s in UPGRADE_SQL.split(";"))):
        op.execute(stmt)


def downgrade() -> None:
    if not _is_postgres():
        return
    for stmt in filter(None, (s.strip() for s in DOWNGRADE_SQL.split(";"))):
        op.execute(stmt)
