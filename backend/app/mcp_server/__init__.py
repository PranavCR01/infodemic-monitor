"""Retrieval MCP server (target design §6 "Retrieval as a shared service", §15).

A thin MCP front end over ``app.core.retrieval``, the same package our LangGraph nodes
import in process. Another team calls the five tools (``map_to_mesh``,
``search_pubmed``, ``fetch_pubmed_records``, ``search_library``, ``rerank_evidence``)
over Streamable HTTP with their own token, scopes and share of the NCBI rate limit.

Layout: ``config`` (settings, client registry), ``quota`` (token buckets),
``schemas`` (tool I/O contract), ``service`` (access control, limits, dispatch; no
MCP code), ``server`` (the MCP wrapper), ``contract`` (schema snapshot checks),
``app`` (wiring from the environment). The MCP SDK is an optional dependency
(``pip install -e ".[mcp]"``); importing this package does not import it.
"""
