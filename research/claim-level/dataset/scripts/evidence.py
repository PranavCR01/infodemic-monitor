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
# E-utilities asks callers to identify themselves with a contact address. It is
# read from the environment so no personal address lives in this public repo;
# unset, requests carry only the tool name (NCBI accepts that).
import os  # noqa: E402
EMAIL = os.environ.get("NCBI_EMAIL", "")

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


def _get(url, **kw):
    """GET with the rate limit applied and a few backoff retries.

    E-utilities intermittently drops TLS connections mid-handshake
    (SSL: UNEXPECTED_EOF_WHILE_READING) under sustained use. One dropped
    connection must not become a missing citation, so each request is retried
    with growing delays before it is allowed to fail.
    """
    last = None
    for attempt in range(5):
        _throttle()
        try:
            r = requests.get(url, **kw)
            if r.status_code in (429, 500, 502, 503, 504):
                last = "HTTP %d" % r.status_code
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            return r
        except Exception as e:
            last = "%s: %s" % (type(e).__name__, str(e)[:120])
            time.sleep(2 ** attempt)
    raise RuntimeError("request failed after 5 attempts (%s): %s"
                       % (last, url))


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
    if kind == "reference" and not rec.get("ok"):
        return rec          # a failed fetch is not evidence; try again later
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
        r = _get(
            "%s/esearch.fcgi" % EUTILS,
            params={"db": "pubmed", "term": query, "retmode": "json",
                    "retmax": retmax, "sort": sort, "tool": TOOL,
                    "email": EMAIL},
            timeout=30,
        )
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        out = {"query": query, "sort": sort, "pmids": ids, "records": []}
        if not ids:
            return out
        s = _get(
            "%s/esummary.fcgi" % EUTILS,
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "json",
                    "tool": TOOL, "email": EMAIL},
            timeout=30,
        )
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
        r = _get(
            "%s/efetch.fcgi" % EUTILS,
            params={"db": "pubmed", "id": pmid, "rettype": "abstract",
                    "retmode": "text", "tool": TOOL, "email": EMAIL},
            timeout=30,
        )
        return {"pmid": pmid, "status": r.status_code, "text": r.text.strip()}

    return _cached("abstract", key, produce)


def pubmed_fulltext(pmid):
    """Open-access full text from PMC, when the paper has a PMCID.

    Many abstracts are too thin to settle a verdict -- BMJ feature articles in
    particular carry a one-line teaser -- and section 7 forbids citing a paper
    for something you have not read. Where PMC has the full text, read it;
    where it does not, the honest answer stays INSUFFICIENT_EVIDENCE.
    """
    key = "fulltext::%s" % pmid

    def produce():
        s = _get("%s/esummary.fcgi" % EUTILS,
                 params={"db": "pubmed", "id": pmid, "retmode": "json",
                         "tool": TOOL, "email": EMAIL}, timeout=30)
        rec = (s.json().get("result", {}) or {}).get(str(pmid), {}) or {}
        pmcid = ""
        for a in rec.get("articleids", []) or []:
            if a.get("idtype") == "pmc":
                pmcid = str(a.get("value", ""))
                break
        if not pmcid:
            return {"pmid": pmid, "pmcid": "", "open_access": False,
                    "text": "", "note": "no PMCID; not open access in PMC"}
        num = pmcid.replace("PMC", "")
        r = _get("%s/efetch.fcgi" % EUTILS,
                 params={"db": "pmc", "id": num, "retmode": "xml",
                         "tool": TOOL, "email": EMAIL}, timeout=60)
        import re as _re
        xml = r.text
        body = _re.sub(r"<(ref-list|back|front)\b.*?</\1>", " ", xml,
                       flags=_re.S | _re.I)
        body = _re.sub(r"<[^>]+>", " ", body)
        body = _re.sub(r"\s+", " ", body).strip()
        return {"pmid": pmid, "pmcid": pmcid,
                "open_access": len(body) > 500,
                "length": len(body), "text": body[:60000]}

    return _cached("fulltext", key, produce)


def fetch_page(url):
    """Fetch a WHO/CDC-style guidance page. Only trusted hosts are allowed, and
    only a 200 with real body text counts as retrieved."""
    host = urllib.parse.urlparse(url).netloc.lower()
    if not any(host == h or host.endswith("." + h) for h in TRUSTED_HOSTS):
        return {"url": url, "ok": False,
                "error": "host %s is not in the trusted list" % host}
    key = "page::%s" % url

    def produce():
        try:
            r = _get(url, timeout=30, headers={
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


# ---------------------------------------------------------------------------
# Section 6 "Trusted sources beyond PubMed": authoritative references for
# claims of kind fact_of_record (a schedule, a legal limit, a statistic, food
# composition, textbook physiology). A fixed allow-list; nothing else is
# fetched. Each snapshot keeps the full text, its SHA-256 and the retrieval
# time, so the quoted passage in reference_citations.csv can be checked against
# exactly what was read.
# ---------------------------------------------------------------------------
REFERENCE_SOURCES = {
    # textbook physiology, standard medical facts
    "ncbi.nlm.nih.gov": "NCBI Bookshelf",
    # vaccination schedules; public-health guidance and fact sheets
    "cdc.gov": "CDC",
    "who.int": "WHO",
    "nhs.uk": "NHS",
    "ecdc.europa.eu": "ECDC",
    # drug, food and supplement rules, safety limits
    "fda.gov": "FDA",
    "ema.europa.eu": "EMA",
    "efsa.europa.eu": "EFSA",
    # food composition
    "fdc.nal.usda.gov": "USDA FoodData Central",
    "api.nal.usda.gov": "USDA FoodData Central",
    # disease statistics: WHO GHO (who.int, above) and national statistics
    # offices
    "seer.cancer.gov": "NCI SEER (US national cancer statistics)",
    "aihw.gov.au": "AIHW (Australian national health statistics)",
    "abs.gov.au": "Australian Bureau of Statistics",
    "ons.gov.uk": "UK Office for National Statistics",
}

# A generic client name: no personal contact details go to outside services.
REF_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _get_ref(url):
    """One rate-limited GET for a reference page. A 4xx is an answer (the page
    is gone or blocks us), so it is not retried; network errors and 5xx are."""
    last = None
    for attempt in range(3):
        _throttle()
        try:
            r = requests.get(url, timeout=45, headers={
                "User-Agent": REF_UA,
                "Accept": "text/html,application/xhtml+xml,application/json"})
            if r.status_code >= 500:
                last = "HTTP %d" % r.status_code
                time.sleep(2 ** attempt)
                continue
            return r
        except Exception as e:
            last = "%s: %s" % (type(e).__name__, str(e)[:120])
            time.sleep(2 ** attempt)
    raise RuntimeError("request failed (%s): %s" % (last, url))


def reference_org(url):
    """The section 6 source a URL belongs to, or None if it is not allowed."""
    host = urllib.parse.urlparse(url).netloc.lower().split(":")[0]
    for h, org in REFERENCE_SOURCES.items():
        if host == h or host.endswith("." + h):
            return org
    return None


def _html_to_text(body):
    import html as _html
    import re
    text = re.sub(r"<(script|style|noscript)\b.*?</\1>", " ", body,
                  flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_reference(url):
    """Fetch an allow-listed reference page and snapshot its full text."""
    org = reference_org(url)
    if not org:
        return {"url": url, "ok": False,
                "error": "not a section 6 reference source"}
    key = "reference::%s" % url

    def produce():
        try:
            r = _get_ref(url)
            ctype = r.headers.get("Content-Type", "")
            if "json" in ctype:
                text = json.dumps(r.json(), ensure_ascii=False)
                title = ""
            else:
                import re
                body = r.text
                text = _html_to_text(body)
                m = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
                title = _html_to_text(m.group(1)) if m else ""
            # Bot walls (NCBI's reCAPTCHA, Akamai "Access Denied") can come
            # back as a 200 with a stub page; that is not the reference.
            blocked = (len(text) < 500 or any(
                s in title.lower() for s in ("checking your browser",
                                             "access denied", "captcha")))
            return {"url": url, "source_org": org,
                    "ok": r.status_code == 200 and not blocked,
                    "status": r.status_code, "title": title,
                    "text_sha256": hashlib.sha256(
                        text.encode("utf-8")).hexdigest(),
                    "text_length": len(text), "text": text}
        except Exception as e:
            return {"url": url, "source_org": org, "ok": False,
                    "error": "%s: %s" % (type(e).__name__, e)}

    return _cached("reference", key, produce)


def load_reference(url):
    """The cached snapshot for url, or None if it was never retrieved."""
    p = _cache_path("reference", "reference::%s" % url)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def snapshot_text(rec):
    """The quotable text of a reference snapshot.

    HTML pages are quoted as fetched. A USDA FoodData Central API record is
    JSON, so it is rendered as one 'Nutrient: amount unit' entry per line,
    after the food's description, which is what a passage quotes.
    """
    text = rec.get("text", "")
    if "api.nal.usda.gov/fdc/" in rec.get("url", ""):
        d = json.loads(text)
        parts = [d.get("description", "")]
        for n in d.get("foodNutrients", []):
            nut = n.get("nutrient", {}) or {}
            if "amount" in n and nut.get("name"):
                parts.append("%s: %s %s" % (nut["name"], n["amount"],
                                            nut.get("unitName", "")))
        return " | ".join(parts)
    return text


def passage_found(passage, text):
    """True if every fragment of a quoted passage occurs in the snapshot.
    Fragments are separated by ' ... ' (words elided between them)."""
    norm = lambda s: " ".join(s.split())
    t = norm(text)
    return all(norm(f) in t for f in passage.split(" ... ") if f.strip())


def bookshelf_search(query, retmax=5):
    """NCBI Bookshelf (StatPearls etc.) through the same E-utilities API."""
    key = "books::%s::%d" % (query, retmax)

    def produce():
        r = _get("%s/esearch.fcgi" % EUTILS,
                 params={"db": "books", "term": query, "retmode": "json",
                         "retmax": retmax, "tool": TOOL}, timeout=30)
        ids = r.json().get("esearchresult", {}).get("idlist", [])
        out = {"query": query, "db": "books", "ids": ids, "records": []}
        if ids:
            s = _get("%s/esummary.fcgi" % EUTILS,
                     params={"db": "books", "id": ",".join(ids),
                             "retmode": "json", "tool": TOOL}, timeout=30)
            res = s.json().get("result", {})
            for i in ids:
                d = res.get(i) or {}
                out["records"].append({
                    "id": i, "title": d.get("title", ""),
                    "book": d.get("booktitle", "") or d.get("book", ""),
                    "accession": d.get("accessionid", "")
                                 or d.get("rid", ""),
                })
        return out

    return _cached("books", key, produce)


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
    elif cmd == "fulltext":
        rec = pubmed_fulltext(sys.argv[2])
        print("pmid=%s pmcid=%s open_access=%s length=%s"
              % (rec["pmid"], rec.get("pmcid"), rec.get("open_access"),
                 rec.get("length")))
        if rec.get("note"):
            print("note:", rec["note"])
        grep = sys.argv[3] if len(sys.argv) > 3 else ""
        text = rec.get("text", "")
        if grep and text:
            import re as _re
            for m in _re.finditer(grep, text, _re.I):
                lo = max(0, m.start() - 300)
                print("...", text[lo:m.end() + 300], "...\n")
        elif text:
            print(text[:5000])
    elif cmd == "fetch":
        rec = fetch_page(sys.argv[2])
        print(json.dumps({k: v for k, v in rec.items() if k != "text"},
                         indent=1))
        if rec.get("ok"):
            print("---- first 1200 chars ----")
            print(rec["text"][:1200])
    elif cmd == "ref":
        rec = fetch_reference(sys.argv[2])
        print(json.dumps({k: v for k, v in rec.items() if k != "text"},
                         indent=1))
        text = rec.get("text", "")
        grep = sys.argv[3] if len(sys.argv) > 3 else ""
        if grep and text:
            import re as _re
            for m in list(_re.finditer(grep, text, _re.I))[:12]:
                lo = max(0, m.start() - 350)
                print("...", text[lo:m.end() + 350], "...\n")
        elif text:
            print(text[:2500])
    elif cmd == "books":
        rec = bookshelf_search(sys.argv[2])
        for r in rec["records"]:
            print(" ", r["id"], r["accession"], "|", r["book"][:40], "|",
                  r["title"][:100])
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
