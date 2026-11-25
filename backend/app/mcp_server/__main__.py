"""Run the retrieval MCP server: ``python -m app.mcp_server`` (Streamable HTTP).

Reads ``PORT`` (default 8080) and the variables listed in ``app.mcp_server.app``.
"""
from __future__ import annotations

import os

import uvicorn


def main() -> None:
    from app.mcp_server.app import create_app

    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "8080")),
                proxy_headers=True, forwarded_allow_ips="*")


if __name__ == "__main__":
    main()
