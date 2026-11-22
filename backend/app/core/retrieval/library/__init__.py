"""The lab's offline library: the fallback when PubMed comes up short (target design §6).

Scanned papers and reports PubMed doesn't index are OCRed, chunked, embedded and stored
in pgvector (an offline batch job, ``ingest``), then searched with hybrid vector +
full-text search (``search``) only when no PubMed paper clears the reranker's threshold
(``fallback``). Plain Python with no LangGraph or MCP code, so the graph's
``rerank_evidence`` node and the MCP server's ``search_library`` tool (T13) share it.

Heavy tools (OCRmyPDF, Tesseract, PyMuPDF, transformers) are imported lazily.
"""
from app.core.retrieval.library.chunking import Chunk, chunk_document, count_tokens
from app.core.retrieval.library.config import LibraryConfig, load_library_config
from app.core.retrieval.library.embeddings import Embedder, HashingEmbedder, MedCptEmbedder, embedder_from_config
from app.core.retrieval.library.fallback import FallbackOutcome, LibraryFallback, should_fire
from app.core.retrieval.library.ingest import (
    IngestOutcome,
    IngestReport,
    LibraryIngestor,
    PubMedDoiLookup,
    PubMedLookup,
)
from app.core.retrieval.library.manifest import ManifestEntry, ManifestError, parse_manifest
from app.core.retrieval.library.ocr import OcrEngine, OcrMyPdfEngine, PageText, TextLayerEngine
from app.core.retrieval.library.search import (
    LibraryHit,
    LibrarySearchResult,
    LibrarySearcher,
    library_evidence_id,
    library_query,
    parse_library_evidence_id,
    search_library,
)
from app.core.retrieval.library.store import (
    InMemoryLibraryStore,
    LibraryDocument,
    LibraryStore,
    PgLibraryStore,
    StoredChunk,
)

__all__ = [
    "Chunk", "Embedder", "FallbackOutcome", "HashingEmbedder", "InMemoryLibraryStore", "IngestOutcome",
    "IngestReport", "LibraryConfig", "LibraryDocument", "LibraryFallback", "LibraryHit", "LibraryIngestor",
    "LibrarySearchResult", "LibrarySearcher", "LibraryStore", "ManifestEntry", "ManifestError",
    "MedCptEmbedder", "OcrEngine", "OcrMyPdfEngine", "PageText", "PgLibraryStore", "PubMedDoiLookup",
    "PubMedLookup", "StoredChunk", "TextLayerEngine", "chunk_document", "count_tokens",
    "embedder_from_config", "library_evidence_id", "library_query", "load_library_config",
    "parse_library_evidence_id", "parse_manifest", "search_library", "should_fire",
]
