"""Make a bearer token for a retrieval MCP server client (design §6 "Per-client access").

Prints the token once (give it to the client over a secure channel; it is not stored
anywhere) and the client entry to add to the server's MCP_CLIENTS / MCP_CLIENTS_FILE,
which holds only the token's SHA-256 hash.

    python scripts/mcp_client_token.py other-team \
        --scopes map_to_mesh search_pubmed fetch_pubmed_records rerank_evidence --ncbi-share 0.3
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.mcp_server.config import TOOL_NAMES, ClientConfig, hash_token, scope_for  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("client_id")
    ap.add_argument("--scopes", nargs="+", choices=TOOL_NAMES, default=[t for t in TOOL_NAMES if t != "search_library"],
                    help="tools this client may call (search_library is opt-in: the library may hold "
                         "copyrighted material)")
    ap.add_argument("--ncbi-share", type=float, default=0.1, help="share of the NCBI rate, 0-1")
    ap.add_argument("--calls-per-minute", type=int, default=None)
    args = ap.parse_args(argv)
    token = secrets.token_urlsafe(32)
    entry = ClientConfig(client_id=args.client_id, token_sha256=hash_token(token),
                         scopes=tuple(scope_for(t) for t in args.scopes), ncbi_share=args.ncbi_share,
                         calls_per_minute=args.calls_per_minute)
    print("token (shown once, give it to the client):", token, file=sys.stderr)
    print(json.dumps(entry.model_dump(mode="json", exclude_none=True)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
