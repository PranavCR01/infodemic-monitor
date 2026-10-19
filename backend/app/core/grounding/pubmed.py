"""Async PubMed grounding — parallel claim queries via httpx + asyncio.gather.

Flow:
    1. Take a list of pre-extracted Claims (identified upstream by the classifier).
    2. Query PubMed ESearch + ESummary for each claim in parallel via asyncio.gather.
    3. Return flat list of PubMedCitation objects, each tagged with its source claim_id.

Best-effort: any failure returns [] rather than crashing the pipeline.
Grounding runs only for MISINFO and DEBUNKING labels (enforced in pipeline/__init__.py).
"""
from __future__ import annotations

import asyncio


import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.schemas.pipeline import Claim, PubMedCitation

_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_NCBI_HEADERS = {"User-Agent": "WHO-Infodemic-Monitor/1.0 (research tool)"}


def _is_http_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


async def ground_transcript(claims: list[Claim]) -> list[PubMedCitation]: 
    """Return PubMed citations for health claims.

    Returns [] on any error — never raises.
    """
    if not claims:
        return []
    await asyncio.sleep(0.4)  
    async with httpx.AsyncClient(timeout=15) as client:
        results = await asyncio.gather(
            *[_staggered_query(client, c.claim_id, c.text, i) for i, c in enumerate(claims)],
            return_exceptions=True,
        )
    citations: list[PubMedCitation] = []
    for r in results:
        if isinstance(r, Exception):
            continue
        citations.extend(r)
    return citations


async def _staggered_query(
    client: httpx.AsyncClient, claim_id: str, claim_text: str, index: int
) -> list[PubMedCitation]:
    """Delay each claim by index * 0.5 s so NCBI requests are staggered, not simultaneous."""
    await asyncio.sleep(index * 0.5)
    return await _query_claim(client, claim_id, claim_text)
    

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception(_is_http_retryable),
    reraise=True,
)
async def _query_claim(client: httpx.AsyncClient, claim_id: str, claim_text: str) -> list[PubMedCitation]:
    esearch_resp = await client.get(
        f"{_EUTILS_BASE}/esearch.fcgi",
        params={
            "db": "pubmed",
            "term": claim_text,
            "retmax": settings.PUBMED_RESULTS_PER_CLAIM,
            "retmode": "json",
          },
        headers=_NCBI_HEADERS,
    )
    esearch_resp.raise_for_status()
    id_list: list[str] = esearch_resp.json().get("esearchresult", {}).get("idlist", [])
    if not id_list:
        return []

    await asyncio.sleep(0.35)  # between ESearch and ESummary for this claim

    esummary_resp = await client.get(
        f"{_EUTILS_BASE}/esummary.fcgi",
        params={"db": "pubmed", "id": ",".join(id_list), "retmode": "json"},
        headers=_NCBI_HEADERS,
    )
    esummary_resp.raise_for_status()

    result_data: dict = esummary_resp.json().get("result", {})
    citations: list[PubMedCitation] = []
    for pmid in id_list:
        entry = result_data.get(pmid, {})
        title = entry.get("title", "").strip()
        if title and pmid:
            citations.append(
                PubMedCitation(
                    claim_id=claim_id,
                    claim=claim_text,
                    title=title,
                    pmid=pmid,
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                )
            )
    return citations
