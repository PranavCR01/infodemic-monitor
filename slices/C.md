# Slice C — Async PubMed Grounding

## Goal
Convert PubMed grounding to fully async with parallel claim queries.
Replace requests + time.sleep with httpx + asyncio.sleep + asyncio.gather.

## Pre-implementation
1. Read CLAUDE.md
2. Read existing `backend/app/core/grounding/pubmed.py` in full
3. Check old repo for any async HTTP patterns to reuse

## Tasks

### C1. backend/pyproject.toml
Add dependency: `httpx>=0.27.0` (if not already added in Slice B)



### C2. backend/app/core/grounding/pubmed.py — full rewrite to async

_extract_claims must call get_provider().classify(...) with a purpose-built claims-extraction prompt (not the full classification prompt). The provider returns a JSON list of 2-3 search query strings. Use the same tenacity retry wrapping already in the provider. Do not add a new HTTP call to any LLM — route through the existing provider abstraction.

Key changes:
- `async def ground_transcript(transcript: str) -> list[PubMedCitation]`
- Use `httpx.AsyncClient` inside an `async with` block
- Replace `time.sleep(N)` with `await asyncio.sleep(N)`
- Extract claims first (still sequential — one LLM call)
- Then run all claim queries in parallel:

```python
async def _query_claim(client, claim: str) -> list[PubMedCitation]:
    # ESearch → ESummary still sequential within a claim
    await asyncio.sleep(0.35)  # between ESearch and ESummary
    ...

# In ground_transcript, after extracting claims:
await asyncio.sleep(0.4)  # before first batch
results = await asyncio.gather(
    *[_query_claim(client, claim) for claim in claims],
    return_exceptions=True  # don't let one failure kill others
)
# flatten results, skip any that are exceptions
```

- Keep best-effort guarantee: `except Exception: return []` at the
  outer level
- Use `settings.PUBMED_RESULTS_PER_CLAIM` instead of hardcoded 2
- Use `settings.PUBMED_RATE_LIMIT_SLEEP` if you add that setting,
  or keep the 0.35/0.4 constants

### C3. backend/app/core/pipeline/__init__.py
- Make `run_pipeline()` `async def` if not already
- `await ground_transcript(transcript)`

### C4. backend/app/worker/tasks.py
Celery tasks are sync. Run the async pipeline:

```python
import asyncio

@celery_app.task
def analyze_video(job_id: str, video_id: str, file_path: str,
                  storage_key: Optional[str] = None):
    # ... file resolution (from Slice B) ...
    result = asyncio.run(run_pipeline(file_path, job_id, video_id))
    # ... persist result ...
```

Do not make the Celery task itself async — `asyncio.run()` is the
correct bridge pattern here.

### C5. Any other callers of ground_transcript or run_pipeline
Search the codebase for all calls. Update each to await properly.

## Definition of Done
- [ ] `ground_transcript` is `async def`
- [ ] Multiple claims are fetched concurrently (asyncio.gather)
- [ ] No `time.sleep` remains in grounding/pubmed.py
- [ ] Worker task uses `asyncio.run(run_pipeline(...))` 
- [ ] A smoke test with a MISINFO video still returns PubMed citations
- [ ] CLAUDE.md updated: Slice C → ✅
