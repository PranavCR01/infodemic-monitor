"""Record whether each TikTok video_url in candidates.csv is still live.

Uses only TikTok's public oEmbed endpoint
(https://www.tiktok.com/oembed?url=<video_url>), one request per second, and
nothing else on TikTok. Writes the result into the row's notes as
"[oEmbed YYYY-MM-DD: live|removed|inconclusive ...]",
replacing any earlier oEmbed note. Does not add or remove rows.

Caveat found 2026-11-22: from some networks the endpoint answers HTTP 200 with a
generic player iframe for ANY numeric ID, including made-up ones, and omits
title/author_name. So the script first queries a control URL with an ID that
cannot exist. A row counts as "live" only if its response carries an
author_name or title; a bare player embed is recorded as "inconclusive", and
only an HTTP error or an explicit error body counts as "removed".

Run:  python research/claim-level/dataset/scripts/check_tiktok_live.py
"""
import csv
import datetime
import io
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "candidates.csv")
EP = "https://www.tiktok.com/oembed?url="
NOTE = re.compile(r"\s*\[oEmbed \d{4}-\d{2}-\d{2}: [^\]]*\]|\s*oEmbed \d{4}-\d{2}-\d{2}: [^.]*\.")


def check(url):
    req = urllib.request.Request(EP + urllib.parse.quote(url, safe=""),
                                 headers={"User-Agent": "research-link-check"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return "removed (HTTP %d)" % e.code
    except Exception as e:  # network trouble: say so, don't call it removed
        return "unchecked (%s)" % type(e).__name__
    if d.get("author_name") or d.get("title"):
        return "live (author %s)" % d.get("author_name", "?")
    if d.get("status_msg") or d.get("code"):
        return "removed (%s)" % (d.get("status_msg") or d.get("code"))
    return ("inconclusive (generic player embed, no title/author; the endpoint "
            "returns the same for a made-up control ID)")



def main():
    with io.open(OUT, encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        cols, rows = rd.fieldnames, list(rd)
    today = datetime.date.today().isoformat()
    control = check("https://www.tiktok.com/@tiktok/video/1000000000000000001")
    print("control (made-up ID):", control)
    time.sleep(1.0)
    tally = {}
    for r in rows:
        u = r["video_url"].strip()
        if "tiktok.com/" not in u:
            continue
        status = check(u)
        tally[status.split(" ")[0]] = tally.get(status.split(" ")[0], 0) + 1
        notes = NOTE.sub("", r["notes"]).rstrip()
        r["notes"] = (notes + " " if notes else "") + \
            "[oEmbed %s: %s]" % (today, status)
        print(status, u)
        time.sleep(1.0)
    with io.open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(tally)


if __name__ == "__main__":
    main()
