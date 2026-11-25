"""Tool limits, enforced in code (§15 "Input and tool limits").

Two layers:

- ``ToolGateway``: the pipeline's only door to retrieval. Only approved functions
  exist; arguments are typed and size-checked; each run has a call budget; each
  call has a hard timeout; results are capped in count and size.
- ``GuardedHttpClient``: the HTTP client retrieval code uses underneath. HTTPS
  only, exact allowed hosts and path prefix, no redirects, a timeout, and the
  response body is read with a byte cap so a huge reply can't be buffered.

Models never reach either: they can't name a tool, a host or a URL. Queries come
from code (retrieval planning) and are validated here anyway, because claim text
in them came from a video.
"""
from __future__ import annotations

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any, Callable, Mapping, Optional
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.core.guardrails.config import ToolLimits, load_guardrails


class ToolLimitError(RuntimeError):
    """A tool call broke a limit. ``kind`` names which one."""

    def __init__(self, kind: str, message: str):
        super().__init__(f"{kind}: {message}")
        self.kind = kind


# ------------------------------------------------------------- tool arguments

_URLISH = re.compile(r"(?:[a-z][a-z0-9+.-]*://|www\.|\\\\|\.\./)", re.IGNORECASE)
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class PubMedSearchArgs(_Args):
    query: str = Field(min_length=1)
    max_results: int = Field(default=10, ge=1)

    @field_validator("query")
    @classmethod
    def _plain_query(cls, v: str) -> str:
        if _URLISH.search(v):
            raise ValueError("query may not contain a URL or path")
        if _CTRL.search(v):
            raise ValueError("query may not contain control characters")
        return v


class PubMedFetchArgs(_Args):
    pmids: list[str] = Field(min_length=1)

    @field_validator("pmids")
    @classmethod
    def _numeric(cls, v: list[str]) -> list[str]:
        for p in v:
            if not re.fullmatch(r"\d{1,9}", p):
                raise ValueError(f"PMID {p!r} is not numeric")
        return list(dict.fromkeys(v))


TOOL_ARGS: dict[str, type[_Args]] = {
    "pubmed_search": PubMedSearchArgs,
    "pubmed_fetch": PubMedFetchArgs,
}

Backend = Callable[..., Any]


class ToolGateway:
    """Calls approved retrieval functions under the configured limits.

    ``backends`` maps tool name to the function that does the work (real PubMed code
    in production, recorded fixtures in tests). A backend registered under a name
    that isn't approved in config is refused at construction.

    One gateway per run: ``calls`` counts toward ``max_calls_per_run``.
    """

    def __init__(self, backends: Mapping[str, Backend], limits: Optional[ToolLimits] = None):
        self.limits = limits or load_guardrails().tools
        unapproved = set(backends) - set(self.limits.approved)
        if unapproved:
            raise ToolLimitError("unapproved_tool", f"not in the approved list: {sorted(unapproved)}")
        unknown = set(backends) - set(TOOL_ARGS)
        if unknown:
            raise ToolLimitError("unapproved_tool", f"no argument schema for: {sorted(unknown)}")
        self._backends = dict(backends)
        self._lock = threading.Lock()
        self.calls = 0
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tool")

    def call(self, name: str, **kwargs: Any) -> list[dict]:
        if name not in self._backends:
            raise ToolLimitError("unapproved_tool", f"{name!r} is not an available tool")
        args = self._validate(name, kwargs)
        with self._lock:
            if self.calls >= self.limits.max_calls_per_run:
                raise ToolLimitError("call_budget", f"run used all {self.limits.max_calls_per_run} tool calls")
            self.calls += 1
        future = self._pool.submit(self._backends[name], **args.model_dump())
        try:
            result = future.result(timeout=self.limits.timeout_seconds)
        except FutureTimeout:
            future.cancel()
            raise ToolLimitError("timeout", f"{name} took longer than {self.limits.timeout_seconds}s") from None
        return self._check_result(name, result)

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    # -- checks --

    def _validate(self, name: str, kwargs: dict) -> _Args:
        lim = self.limits
        try:
            args = TOOL_ARGS[name].model_validate(kwargs)
        except ValidationError as exc:
            raise ToolLimitError("bad_arguments", f"{name}: {exc.errors()[0]['msg']}") from None
        if isinstance(args, PubMedSearchArgs):
            if len(args.query) > lim.max_query_chars:
                raise ToolLimitError("query_too_long", f"{len(args.query)} chars > {lim.max_query_chars}")
            if len(args.query.split()) > lim.max_query_terms:
                raise ToolLimitError("query_too_long", f"more than {lim.max_query_terms} terms")
            if args.max_results > lim.max_results:
                args = args.model_copy(update={"max_results": lim.max_results})
        if isinstance(args, PubMedFetchArgs) and len(args.pmids) > lim.max_results:
            raise ToolLimitError("too_many_ids", f"{len(args.pmids)} PMIDs > {lim.max_results}")
        return args

    def _check_result(self, name: str, result: Any) -> list[dict]:
        if not isinstance(result, list) or not all(isinstance(r, dict) for r in result):
            raise ToolLimitError("bad_response", f"{name} must return a list of records")
        size = len(json.dumps(result, default=str).encode())
        if size > self.limits.max_response_bytes:
            raise ToolLimitError("response_too_large", f"{size} bytes > {self.limits.max_response_bytes}")
        return result[: self.limits.max_results]


# ---------------------------------------------------------------- HTTP layer


def check_url(url: str, limits: ToolLimits) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise ToolLimitError("host_not_allowed", f"only https is allowed, got {parts.scheme!r}")
    if parts.username or parts.password:
        raise ToolLimitError("host_not_allowed", "credentials in URLs are not allowed")
    host = (parts.hostname or "").lower()
    if host not in limits.allowed_hosts:
        raise ToolLimitError("host_not_allowed", f"{host!r} is not an allowed host")
    if parts.port not in (None, 443):
        raise ToolLimitError("host_not_allowed", f"port {parts.port} is not allowed")
    if not parts.path.startswith(limits.allowed_path_prefix) or ".." in parts.path:
        raise ToolLimitError("host_not_allowed", f"path {parts.path!r} is outside {limits.allowed_path_prefix}")


def _read_capped(chunks, cap: int) -> bytes:
    buf = bytearray()
    for chunk in chunks:
        buf.extend(chunk)
        if len(buf) > cap:
            raise ToolLimitError("response_too_large", f"response exceeded {cap} bytes")
    return bytes(buf)


def _copy(resp: httpx.Response, body: bytes) -> httpx.Response:
    # The body is already decoded, so the encoding headers no longer describe it.
    headers = {k: v for k, v in resp.headers.items() if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")}
    return httpx.Response(resp.status_code, headers=headers, content=body, request=resp.request)


class GuardedHttpClient:
    """``httpx.Client`` with the allowlist, timeout, no redirects and a body cap."""

    def __init__(self, limits: Optional[ToolLimits] = None, *, transport: httpx.BaseTransport | None = None,
                 headers: Optional[dict] = None):
        self.limits = limits or load_guardrails().tools
        self._client = httpx.Client(
            timeout=httpx.Timeout(self.limits.timeout_seconds),
            follow_redirects=False,
            transport=transport,
            headers=headers,
        )

    def get(self, url: str, params: Optional[dict] = None) -> httpx.Response:
        check_url(url, self.limits)
        try:
            with self._client.stream("GET", url, params=params) as resp:
                if resp.is_redirect:
                    raise ToolLimitError("redirect_refused", f"{resp.status_code} to {resp.headers.get('location')!r}")
                declared = resp.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > self.limits.max_response_bytes:
                    raise ToolLimitError("response_too_large", f"declared {declared} bytes")
                body = _read_capped(resp.iter_bytes(), self.limits.max_response_bytes)
                return _copy(resp, body)
        except httpx.TimeoutException:
            raise ToolLimitError("timeout", f"no response within {self.limits.timeout_seconds}s") from None

    def close(self) -> None:
        self._client.close()


class AsyncGuardedHttpClient:
    """Async twin of ``GuardedHttpClient`` (today's PubMed code is async)."""

    def __init__(self, limits: Optional[ToolLimits] = None, *, transport: httpx.AsyncBaseTransport | None = None,
                 headers: Optional[dict] = None):
        self.limits = limits or load_guardrails().tools
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.limits.timeout_seconds),
            follow_redirects=False,
            transport=transport,
            headers=headers,
        )

    async def get(self, url: str, params: Optional[dict] = None) -> httpx.Response:
        check_url(url, self.limits)
        try:
            async with self._client.stream("GET", url, params=params) as resp:
                if resp.is_redirect:
                    raise ToolLimitError("redirect_refused", f"{resp.status_code} to {resp.headers.get('location')!r}")
                buf = bytearray()
                async for chunk in resp.aiter_bytes():
                    buf.extend(chunk)
                    if len(buf) > self.limits.max_response_bytes:
                        raise ToolLimitError("response_too_large", f"response exceeded {self.limits.max_response_bytes} bytes")
                return _copy(resp, bytes(buf))
        except httpx.TimeoutException:
            raise ToolLimitError("timeout", f"no response within {self.limits.timeout_seconds}s") from None

    async def aclose(self) -> None:
        await self._client.aclose()
