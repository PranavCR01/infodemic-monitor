"""The CSV manifest researchers upload with their scans (§6 "Building the library" step 1).

Columns (header row required; names are case-insensitive):

    file, title, authors, year, doi, pmid, study_type

``file`` and ``title`` are required. ``authors`` is a ``;``-separated list. ``study_type``
comes from a person, because scans carry no PubMed tags: either a PubMed publication
type ("Randomized Controlled Trial", "Systematic Review", ...) or one of the reranker's
own names (``rct``, ``observational``, ``animal``, ``in_vitro``, ...). Left empty it is
``unknown``, which ranks below every tagged type.

Bad rows are reported, not silently dropped, and never stop the other rows.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from app.core.retrieval.rerank import StudyType, _from_types

REQUIRED_COLUMNS = ("file", "title")
KNOWN_COLUMNS = ("file", "title", "authors", "year", "doi", "pmid", "study_type")
MAX_TITLE = 500

_DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.I)
_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")


class ManifestEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    row: int  # 1-based data row (the header is row 0)
    file: str
    title: str
    authors: tuple[str, ...] = ()
    year: Optional[int] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    study_type: Optional[str] = None  # a StudyType value, or None (unknown)
    study_type_raw: str = ""
    publication_type: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class ManifestError:
    row: int
    message: str


def normalize_doi(value: str) -> Optional[str]:
    v = _DOI_PREFIX.sub("", (value or "").strip()).strip().lower()
    if not v:
        return None
    if not _DOI_RE.match(v):
        raise ValueError(f"not a DOI: {value!r}")
    return v


def normalize_pmid(value: str) -> Optional[str]:
    v = (value or "").strip()
    if not v:
        return None
    if not v.isdigit() or len(v) > 9:
        raise ValueError(f"not a PMID: {value!r}")
    return v.lstrip("0") or None


def parse_study_type(value: str) -> Optional[StudyType]:
    v = (value or "").strip()
    if not v or v.lower() in {"unknown", "none", "n/a", "na"}:
        return None
    st = _from_types({v.lower()})
    if st is None:
        raise ValueError(f"unrecognised study type {value!r}")
    return st


def _safe_file(value: str) -> str:
    v = (value or "").strip()
    p = PurePath(v)
    if not v or p.is_absolute() or ".." in p.parts or "\\" in v:
        raise ValueError(f"file must be a plain relative path inside the upload: {value!r}")
    if p.suffix.lower() != ".pdf":
        raise ValueError(f"file must be a PDF: {value!r}")
    return v


def parse_manifest(source: Union[str, Path, io.TextIOBase]) -> tuple[list[ManifestEntry], list[ManifestError]]:
    """Parse a manifest from a path, a file object or CSV text."""
    if isinstance(source, Path) or (isinstance(source, str) and "\n" not in source and source.endswith(".csv")):
        text = Path(source).read_text(encoding="utf-8-sig")
    elif isinstance(source, str):
        text = source
    else:
        text = source.read()
    reader = csv.DictReader(io.StringIO(text))
    header = [h.strip().lower() for h in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        return [], [ManifestError(0, f"missing required columns: {', '.join(missing)}")]
    unknown = [h for h in header if h not in KNOWN_COLUMNS]
    errors: list[ManifestError] = []
    if unknown:
        errors.append(ManifestError(0, f"ignored unknown columns: {', '.join(unknown)}"))

    entries: list[ManifestEntry] = []
    seen_files: set[str] = set()
    for i, raw in enumerate(reader, start=1):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items() if k is not None}
        if not any(row.values()):
            continue
        try:
            file = _safe_file(row.get("file", ""))
            if file in seen_files:
                raise ValueError(f"file listed twice: {file}")
            title = row.get("title", "")
            if not title:
                raise ValueError("title is required")
            year = None
            if row.get("year"):
                if not re.fullmatch(r"\d{4}", row["year"]) or not 1800 <= int(row["year"]) <= 2100:
                    raise ValueError(f"not a year: {row['year']!r}")
                year = int(row["year"])
            st = parse_study_type(row.get("study_type", ""))
            entry = ManifestEntry(
                row=i,
                file=file,
                title=title[:MAX_TITLE],
                authors=tuple(a.strip() for a in row.get("authors", "").split(";") if a.strip()),
                year=year,
                doi=normalize_doi(row.get("doi", "")),
                pmid=normalize_pmid(row.get("pmid", "")),
                study_type=st.value if st else None,
                study_type_raw=row.get("study_type", ""),
                publication_type=[st.value] if st else [],
            )
        except ValueError as exc:
            errors.append(ManifestError(i, str(exc)))
            continue
        seen_files.add(file)
        entries.append(entry)
    return entries, errors
