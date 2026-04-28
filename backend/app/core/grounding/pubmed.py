"""Async PubMed grounding — parallel claim queries via httpx + asyncio.gather.

Flow:
  1. Call configured LLM provider to extract 2-3 PubMed search queries from transcript.
  2. Query PubMed ESearch + ESummary for each claim in parallel via asyncio.gather.
  3. Return flat list of PubMedCitation objects.

Best-effort: any failure returns [] rather than crashing the pipeline.
Grounding runs only for MISINFO and DEBUNKING labels (enforced in pipeline/__init__.py).
"""
from __future__ import annotations

import asyncio
import json
import re

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.schemas.pipeline import PubMedCitation

_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_MAX_TRANSCRIPT_CHARS = 3_000
_NCBI_HEADERS = {"User-Agent": "WHO-Infodemic-Monitor/1.0 (research tool)"}

_CLAIMS_SYSTEM_PROMPT = """\
You are a biomedical search assistant.

Given the health-related transcript below, extract 2-3 specific, verifiable health \
claims that could be looked up in PubMed.

Respond ONLY with a JSON array of short search query strings (no markdown, no prose).
Each string should be 3-7 words, suitable as a PubMed search term.

Example output:
["electrolytes water fluid retention", "vitamin D immune response", "seed oils cardiovascular risk"]
"""


def _is_llm_retryable(exc: BaseException) -> bool:
    try:
        import openai
        if isinstance(exc, (openai.APIConnectionError, openai.InternalServerError)):
            return True
    except ImportError:
        pass
    try:
        import anthropic
        if isinstance(exc, (anthropic.APIConnectionError, anthropic.InternalServerError)):
            return True
    except ImportError:
        pass
    return False


def _is_http_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


async def ground_transcript(transcript: str) -> list[PubMedCitation]:
    """Return PubMed citations for health claims in transcript.

    Returns [] on any error — never raises.
    """
    if not transcript or not transcript.strip():
        return []

    try:
        claims = await _extract_claims(transcript)
    except Exception:
        return []

    if not claims:
        return []

    await asyncio.sleep(0.4)  # brief pause before first NCBI batch

    async with httpx.AsyncClient(timeout=15) as client:
        results = await asyncio.gather(
            *[_query_claim(client, claim) for claim in claims],
            return_exceptions=True,
        )

    citations: list[PubMedCitation] = []
    for r in results:
        if isinstance(r, Exception):
            continue
        citations.extend(r)
    return citations


async def _extract_claims(transcript: str) -> list[str]:
    """Route through configured LLM provider to extract PubMed search queries."""
    text = transcript[:_MAX_TRANSCRIPT_CHARS]
    if len(transcript) > _MAX_TRANSCRIPT_CHARS:
        text += "\n[truncated]"
    return await asyncio.to_thread(_extract_claims_sync, text)


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception(_is_llm_retryable),
    reraise=True,
)
def _extract_claims_sync(text: str) -> list[str]:
    """Sync LLM call — run via asyncio.to_thread. Uses configured provider credentials."""
    if settings.INFERENCE_PROVIDER == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            system=_CLAIMS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
        )
        raw = resp.content[0].text if resp.content else ""
    else:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _CLAIMS_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0,
        )
        raw = resp.choices[0].message.content or ""
    return _parse_claims(raw)


def _parse_claims(text: str) -> list[str]:
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    for m in re.finditer(r"\[.*?\]", cleaned, flags=re.DOTALL):
        try:
            result = json.loads(m.group(0))
            if isinstance(result, list):
                return [str(c).strip() for c in result if str(c).strip()][:3]
        except Exception:
            continue
    return []


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception(_is_http_retryable),
    reraise=True,
)
async def _query_claim(client: httpx.AsyncClient, claim: str) -> list[PubMedCitation]:
    """ESearch then ESummary for one claim; sequential within claim, parallel across claims."""
    esearch_resp = await client.get(
        f"{_EUTILS_BASE}/esearch.fcgi",
        params={
            "db": "pubmed",
            "term": claim,
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
                    claim=claim,
                    title=title,
                    pmid=pmid,
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                )
            )
    return citations
