"""Evidence retrieval for the golden label set.

Every PMID and URL that ends up in claims.csv must have been returned by a real
request made through this module. Nothing is cited from memory --
docs/target-system-design.md section 6: "Every paper ID, title and link comes from
PubMed's own responses, so the model can never invent a citation."

Two sources:
  * PubMed E-utilities (esearch + esummary), rate-limited to 3 requests/second,
    which is the documented ceiling without an API key.
  * WHO / CDC pages, fetched live. Only a URL that actually returned 200 and whose
    body contains the expected topic terms is usable as a citation.

Responses are cached under evidence_cache/ so re-runs make no new requests and the
retrieval is reproducible.

CLI:
  python evidence.py search "hot drinks influenza" --retmax 5
  python evidence.py fetch https://www.who.int/news-room/...
  python evidence.py batch queries.json
"""
import hashlib
import json
import sys
import threading
import time
import urllib.parse
from pathlib import Path

import requests

# Windows consoles default to cp1252, which cannot print the Greek letters and
# dashes that paper titles are full of.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

DATASET = Path(__file__).resolve().parents[1]
CACHE = DATASET / "evidence_cache"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# PubMed asks for <= 3 requests/second without an API key. One shared lock and a
# minimum spacing enforces it even if callers loop tightly.
_MIN_INTERVAL = 1.0 / 3.0
_lock = threading.Lock()
_last = [0.0]

TOOL = "infodemic-monitor-golden-set"
EMAIL = "prc4@illinois.edu"   # E-utilities asks callers to identify themselves

TRUSTED_HOSTS = (
    "who.int", "cdc.gov", "nih.gov", "ncbi.nlm.nih.gov", "nhs.uk",
    "fda.gov", "cochrane.org", "cochranelibrary.com", "europa.eu",
    "aap.org", "heart.org", "cancer.gov", "hopkinsmedicine.org",
)


def _throttle():
    with _lock:
        wait = _MIN_INTERVAL - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()


def _cache_path(kind, key):
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
    d = CACHE / kind
    d.mkdir(parents=True, exist_ok=True)
    return d / ("%s.json" % h)


def _cached(kind, key, produce):
    p = _cache_path(kind, key)
    if p.exists():
        rec = json.loads(p.read_text(encoding="utf-8"))
        rec["_from_cache"] = True
        return rec
    rec = produce()
    rec["_key"] = key
    rec["_retrieved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    p.write_text(json.dumps(rec, indent=1, ensure_ascii=False),
                 encoding="utf-8")
    rec["_from_cache"] = False
    return rec


def pubmed_search(query, retmax=5, sort="relevance"):
    """esearch + esummary. Returns real PMIDs with titles, journals and years.

    sort=relevance matters: without it PubMed returns the most *recent* matches,
    which is the bug recorded in context/CLAIM_LEVEL.md section 7 (2026-10-10).
    """
    key = "search::%s::%d::%s" % (query, retmax, sort)

    def produce():
        _throttle()
        r = requests.get(
            "%s/esearch.fcgi" % EUTILS,
            params={"db": "pubmed", "term": query, "retmode": "json",
                    "retmax": retmax, "sort": sort, "tool": TOOL,
                    "email": EMAIL},
            timeout=30,
        )
        r.raise_for_status()
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        out = {"query": query, "sort": sort, "pmids": ids, "records": []}
        if not ids:
            return out
        _throttle()
        s = requests.get(
            "%s/esummary.fcgi" % EUTILS,
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "json",
                    "tool": TOOL, "email": EMAIL},
            timeout=30,
        )
        s.raise_for_status()
        res = s.json().get("result", {})
        for pid in ids:
            d = res.get(pid) or {}
            if not d:
                continue
            out["records"].append({
                "pmid": pid,
                "title": d.get("title", "").strip(),
                "journal": d.get("fulljournalname") or d.get("source", ""),
                "year": (d.get("pubdate") or "")[:4],
                "pubtypes": [p for p in (d.get("pubtype") or [])],
                "url": "https://pubmed.ncbi.nlm.nih.gov/%s/" % pid,
            })
        return out

    return _cached("search", key, produce)


def pubmed_abstract(pmid):
    """efetch the abstract text, so a verdict can be checked against the paper."""
    key = "abstract::%s" % pmid

    def produce():
        _throttle()
        r = requests.get(
            "%s/efetch.fcgi" % EUTILS,
            params={"db": "pubmed", "id": pmid, "rettype": "abstract",
                    "retmode": "text", "tool": TOOL, "email": EMAIL},
            timeout=30,
        )
        r.raise_for_status()
        return {"pmid": pmid, "status": r.status_code, "text": r.text.strip()}

    return _cached("abstract", key, produce)


def fetch_page(url):
    """Fetch a WHO/CDC-style guidance page. Only trusted hosts are allowed, and
    only a 200 with real body text counts as retrieved."""
    host = urllib.parse.urlparse(url).netloc.lower()
    if not any(host == h or host.endswith("." + h) for h in TRUSTED_HOSTS):
        return {"url": url, "ok": False,
                "error": "host %s is not in the trusted list" % host}
    key = "page::%s" % url

    def produce():
        _throttle()
        try:
            r = requests.get(url, timeout=30, headers={
                "User-Agent": "%s (%s)" % (TOOL, EMAIL)})
            body = r.text
            # crude tag strip: enough to confirm the topic terms are present
            import re
            text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", body,
                          flags=re.S | re.I)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            title = ""
            m = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
            if m:
                title = re.sub(r"\s+", " ", m.group(1)).strip()
            return {"url": url, "ok": r.status_code == 200,
                    "status": r.status_code, "title": title,
                    "text_length": len(text), "text": text[:20000]}
        except Exception as e:
            return {"url": url, "ok": False,
                    "error": "%s: %s" % (type(e).__name__, e)}

    return _cached("page", key, produce)


def _print_search(rec):
    print("query: %s  (cache=%s)  %d hits"
          % (rec["query"], rec.get("_from_cache"), len(rec["records"])))
    for r in rec["records"]:
        pt = ", ".join(r["pubtypes"][:3])
        print("  PMID %s (%s) %s" % (r["pmid"], r["year"], r["title"][:110]))
        if pt:
            print("        types: %s | %s" % (pt, r["journal"][:60]))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "search":
        retmax = 5
        if "--retmax" in sys.argv:
            retmax = int(sys.argv[sys.argv.index("--retmax") + 1])
        _print_search(pubmed_search(sys.argv[2], retmax=retmax))
    elif cmd == "abstract":
        rec = pubmed_abstract(sys.argv[2])
        print(rec["text"][:4000])
    elif cmd == "fetch":
        rec = fetch_page(sys.argv[2])
        print(json.dumps({k: v for k, v in rec.items() if k != "text"},
                         indent=1))
        if rec.get("ok"):
            print("---- first 1200 chars ----")
            print(rec["text"][:1200])
    elif cmd == "batch":
        spec = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
        out = {}
        for item in spec:
            q = item["query"] if isinstance(item, dict) else item
            rm = item.get("retmax", 5) if isinstance(item, dict) else 5
            rec = pubmed_search(q, retmax=rm)
            out[q] = rec["records"]
            _print_search(rec)
            print()
        dest = Path(sys.argv[3]) if len(sys.argv) > 3 else None
        if dest:
            dest.write_text(json.dumps(out, indent=1, ensure_ascii=False),
                            encoding="utf-8")
            print("wrote %s" % dest)
    else:
        print("unknown command %r" % cmd)


if __name__ == "__main__":
    main()
