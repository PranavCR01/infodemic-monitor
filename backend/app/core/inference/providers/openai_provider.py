"""OpenAI inference provider — GPT chat completions with JSON mode."""
from __future__ import annotations

import json
import re
import time

import openai
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.exceptions import InferenceProviderError
from app.core.schemas.pipeline import ClassificationResult, FusionResult, MisinfoLabel


def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, (openai.APIConnectionError, openai.InternalServerError))

_SYSTEM_PROMPT = """\
You are a public-health fact-checking assistant.

Analyze the video content and respond with a JSON object containing exactly these keys:
- "label": one of "MISINFO", "NO_MISINFO", "DEBUNKING", "CANNOT_RECOGNIZE"
- "confidence": float between 0.0 and 1.0
- "explanation": 2-4 sentence explanation of your decision
- "evidence_snippets": array of 1-3 exact quotes from the content

Labels:
- MISINFO: video contains false or misleading health information
- NO_MISINFO: video contains accurate health information
- DEBUNKING: video explicitly corrects misinformation
- CANNOT_RECOGNIZE: cannot determine (insufficient content)
"""


class OpenAIProvider:
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key, max_retries=0)  # tenacity owns retries
        self._model = model

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )
    def classify(self, fusion: FusionResult) -> ClassificationResult:
        try:
            start = time.time()
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": fusion.combined_content or fusion.transcript},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            latency_ms = int((time.time() - start) * 1000)
            content = resp.choices[0].message.content or ""
            parsed = _parse_json(content)
            return ClassificationResult(
                label=_safe_label(parsed.get("label")),
                confidence=float(parsed.get("confidence", 0.5)),
                explanation=str(parsed.get("explanation", "")),
                evidence_snippets=_safe_list(parsed.get("evidence_snippets")),
                provider="openai",
                model_used=self._model,
                latency_ms=latency_ms,
            )
        except (openai.APIConnectionError, openai.InternalServerError):
            raise  # let tenacity handle retryable errors
        except Exception as exc:
            raise InferenceProviderError(provider="openai", cause=exc) from exc


def _parse_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    for m in re.finditer(r"\{.*\}", cleaned, flags=re.DOTALL):
        try:
            return json.loads(m.group(0))
        except Exception:
            continue
    return {}


def _safe_label(raw) -> MisinfoLabel:
    try:
        return MisinfoLabel(str(raw).strip().upper().rstrip("."))
    except Exception:
        return MisinfoLabel.CANNOT_RECOGNIZE


def _safe_list(raw) -> list[str]:
    if isinstance(raw, list):
        return [str(i).strip() for i in raw if str(i).strip()]
    if isinstance(raw, str):
        return [s.strip() for s in raw.split("\n") if s.strip()]
    return []
