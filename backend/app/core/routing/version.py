"""Traceable analysis version (T36, design §12 and §14).

Each graph result records which code and which routing produced it::

    graph_v1+<short git sha>+p<8-char routing hash>      e.g. graph_v1+3f9c2ab+p1a2b3c4d

* the base (``GRAPH_PIPELINE_VERSION``, ``graph_v1``) names the graph design;
* the git sha comes from ``RAILWAY_GIT_COMMIT_SHA`` (set by Railway on deploy), else
  ``GIT_SHA``, else ``unknown``; it is the only environment value read here;
* the ``p`` hash covers the prompt version and model routing of every LLM step plus
  the fallback policy in ``config/routing.yaml`` (canonical JSON, sorted keys).
  Prices are left out: they change the cost report, not the analysis.

The full routing snapshot (what the hash covers, plus the routing file's ``version``
label) is stored on the result row so a printed report can be reproduced.
The routing config holds no credentials (keys come from settings, not routing.yaml);
step ``params`` are copied with any key-like entry dropped, as a second guard.

Rows written before T36 carry the plain ``graph_v1``; ``parse_analysis_version``
accepts both forms.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from app.core.routing.config import RoutingConfig

SNAPSHOT_SCHEMA = 1
UNKNOWN_SHA = "unknown"
SHORT_SHA_LEN = 7
HASH_LEN = 8
GIT_SHA_ENV_VARS = ("RAILWAY_GIT_COMMIT_SHA", "GIT_SHA")

_SHA_RE = re.compile(r"^[0-9a-fA-F]{4,64}$")
_SECRET_PARAM_RE = re.compile(r"key|token|secret|password|credential|auth", re.IGNORECASE)
_VERSION_RE = re.compile(r"^(?P<base>[^+]+)\+(?P<sha>[^+]+)\+p(?P<hash>[0-9a-f]{%d})$" % HASH_LEN)


def git_short_sha(env: Optional[Mapping[str, str]] = None) -> str:
    """Short commit sha of the deployed code, or ``unknown``.

    Only the two sha variables are read. A value that is not a hex sha is ignored,
    so nothing else from the environment can end up in a stored version string."""
    env = os.environ if env is None else env
    for name in GIT_SHA_ENV_VARS:
        value = (env.get(name) or "").strip()
        if value and _SHA_RE.match(value):
            return value[:SHORT_SHA_LEN].lower()
    return UNKNOWN_SHA


def _safe_params(params: Mapping[str, Any]) -> dict:
    return {k: v for k, v in params.items() if not _SECRET_PARAM_RE.search(str(k))}


def routing_snapshot(config: RoutingConfig) -> dict:
    """Prompt version and model routing per LLM step, the fallback policy, the routing
    file's version label and the hash of the routed part. JSON-serialisable."""
    steps: dict[str, dict] = {}
    for name in sorted(config.steps):
        route = config.steps[name]
        entry: dict[str, Any] = {"provider": route.provider, "model": route.model, "prompt": route.prompt}
        if route.fallback is not None:
            entry["fallback"] = {"provider": route.fallback.provider, "model": route.fallback.model}
        params = _safe_params(route.params or {})
        if params:
            entry["params"] = params
        steps[name] = entry
    fb = config.fallback
    fallback: dict[str, Any] = {"on": sorted(fb.on), "retries": fb.retries}
    if fb.use is not None:
        fallback["use"] = {"provider": fb.use.provider, "model": fb.use.model}
    routed = {"steps": steps, "fallback": fallback}
    return {
        "schema": SNAPSHOT_SCHEMA,
        "routing_version": config.version,
        "routing_status": config.status,
        **routed,
        "hash": routing_hash(routed),
    }


def routing_hash(routed: Mapping[str, Any]) -> str:
    """First 8 hex chars of sha256 over the canonical JSON of ``steps`` and ``fallback``."""
    payload = {"steps": routed.get("steps") or {}, "fallback": routed.get("fallback") or {}}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:HASH_LEN]


def analysis_version(base: str, config: RoutingConfig, *, env: Optional[Mapping[str, str]] = None) -> str:
    """``<base>+<short sha>+p<hash>`` for this deploy and routing table."""
    return f"{base}+{git_short_sha(env)}+p{routing_snapshot(config)['hash']}"


@dataclass(frozen=True)
class AnalysisVersion:
    base: str
    git_sha: Optional[str] = None       # None on pre-T36 rows ("graph_v1")
    routing_hash: Optional[str] = None

    @property
    def traceable(self) -> bool:
        return self.git_sha is not None


def parse_analysis_version(value: Optional[str]) -> Optional[AnalysisVersion]:
    """Split a stored version. Old values (``graph_v1``, ``graph-v1``) parse as a base
    with no sha or hash; ``None`` stays ``None``."""
    if not value:
        return None
    m = _VERSION_RE.match(value)
    if not m:
        return AnalysisVersion(base=value)
    return AnalysisVersion(base=m["base"], git_sha=m["sha"], routing_hash=m["hash"])


def snapshot_matches(version: Optional[str], snapshot: Optional[Mapping[str, Any]]) -> bool:
    """True when ``snapshot`` is the routing that ``version`` names (same hash)."""
    parsed = parse_analysis_version(version)
    return bool(parsed and parsed.routing_hash and snapshot and snapshot.get("hash") == parsed.routing_hash)
