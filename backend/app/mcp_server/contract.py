"""Tool names and schemas as a contract (design §6 "Versioning").

``contract/tools.json`` is the published snapshot: every tool's input and output JSON
Schema. The contract test (``test_mcp_server.py``) compares the live server against
it:

- identical: pass;
- additive (a new tool, a new optional input field, a new output field): fail with a
  message to refresh the snapshot (``python -m app.mcp_server.contract --write``);
- breaking (a tool removed, a field removed or retyped, a new required input, a
  tighter constraint): fail with a message to ship the change under a new tool name
  and keep the old one until callers migrate.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

SNAPSHOT_PATH = Path(__file__).resolve().parent / "contract" / "tools.json"
_IGNORED_KEYS = {"title", "description", "examples"}


def _resolve(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            target = defs[ref.split("/")[-1]]
            merged = {**target, **{k: v for k, v in node.items() if k != "$ref"}}
            return _resolve(merged, defs)
        return {k: _resolve(v, defs) for k, v in node.items() if k != "$defs"}
    if isinstance(node, list):
        return [_resolve(v, defs) for v in node]
    return node


def normalize(schema: dict[str, Any] | None) -> dict[str, Any]:
    """Refs inlined, titles and descriptions dropped: what callers depend on."""
    if not schema:
        return {}
    resolved = _resolve(schema, schema.get("$defs", {}))

    def strip(node: Any) -> Any:
        if isinstance(node, dict):
            # Metadata keys hold strings; a *property* named "title" holds a schema.
            return {k: strip(v) for k, v in node.items() if not (k in _IGNORED_KEYS and isinstance(v, str))}
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node

    return strip(resolved)


async def _live_async() -> dict[str, Any]:
    from app.mcp_server.app import build_default_server

    server = build_default_server(clients_env={}, public_url=None, library=False, env={})
    tools = await server.list_tools()
    return {
        "tools": {
            t.name: {"input_schema": t.input_schema, "output_schema": t.output_schema}
            for t in sorted(tools, key=lambda t: t.name)
        }
    }


def live_contract() -> dict[str, Any]:
    return asyncio.run(_live_async())


def load_snapshot(path: Path = SNAPSHOT_PATH) -> dict[str, Any]:
    return json.loads(path.read_text())


def _props(schema: dict) -> tuple[dict, set]:
    return schema.get("properties", {}), set(schema.get("required", []))


def breaking_changes(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """Changes to existing tools that would break a caller."""
    out: list[str] = []
    for name, old_tool in old.get("tools", {}).items():
        new_tool = new.get("tools", {}).get(name)
        if new_tool is None:
            out.append(f"{name}: tool removed")
            continue
        oi, ni = normalize(old_tool.get("input_schema")), normalize(new_tool.get("input_schema"))
        (op, oreq), (np_, nreq) = _props(oi), _props(ni)
        for field in op:
            if field not in np_:
                out.append(f"{name}: input field {field!r} removed")
            elif op[field] != np_[field]:
                out.append(f"{name}: input field {field!r} changed")
        for field in nreq - oreq:
            out.append(f"{name}: input field {field!r} is now required")
        oo, no = normalize(old_tool.get("output_schema")), normalize(new_tool.get("output_schema"))
        (op, oreq), (np_, nreq) = _props(oo), _props(no)
        for field in op:
            if field not in np_:
                out.append(f"{name}: output field {field!r} removed")
            elif op[field] != np_[field]:
                out.append(f"{name}: output field {field!r} changed")
        for field in oreq - nreq:
            out.append(f"{name}: output field {field!r} is no longer always present")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check or refresh the MCP tool contract snapshot")
    ap.add_argument("--write", action="store_true", help="overwrite contract/tools.json with the live schemas")
    ap.add_argument("--baseline", type=Path, default=SNAPSHOT_PATH,
                    help="snapshot to compare against (e.g. one exported from the main branch)")
    args = ap.parse_args(argv)
    live = live_contract()
    if args.write:
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(json.dumps(live, indent=2, sort_keys=True) + "\n")
        print(f"wrote {SNAPSHOT_PATH}")
        return 0
    broken = breaking_changes(load_snapshot(args.baseline), live)
    for b in broken:
        print("BREAKING:", b)
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
