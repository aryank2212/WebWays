"""Survey GitHub for existing torrent/magnet creation tools before building our own.

    python3 scripts/research/github_survey.py > docs/research/github-survey-data.md

Uses the unauthenticated GitHub search API (10 requests/minute), so it sleeps between queries.
The *decision* drawn from this data is written up by hand in docs/research/github-survey.md.
"""
from __future__ import annotations

import datetime
import json
import time
import urllib.parse
import urllib.request

HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "webways-research"}
QUERIES = [
    "create torrent file drag drop",
    "torrent creator in:name,description",
    "create-torrent webtorrent",
    "magnet link generator torrent file",
    "mktorrent",
    "torrent file parser magnet in:description language:javascript",
    "torrent creation library python",
    "torrent maker gui",
    "torf torrent python in:name",
    "dottorrent",
    "drag and drop torrent create in:description",
    "torrent creator web app browser in:description",
    "magnet uri generator in:description",
    "bittorrent v2 hybrid torrent create in:description",
]
# Repos looked at individually (license, activity) because they came up or are already dependencies.
INSPECT = ["webtorrent/create-torrent", "webtorrent/parse-torrent", "rndusr/torf", "alexpdev/torrentfile",
           "arvidn/libtorrent", "Kimbatt/torrent-creator", "kz26/dottorrent", "pobrn/mktorrent"]


def get(url: str):
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=20) as r:
        return json.load(r)


def row(r: dict) -> str:
    lic = (r["license"] or {}).get("spdx_id") or "none"
    desc = (r["description"] or "").replace("|", "/")[:100]
    flag = " (archived)" if r["archived"] else ""
    return f"| [{r['full_name']}]({r['html_url']}) | {r['stargazers_count']} | {lic} | {r['language'] or '-'} | {r['pushed_at'][:10]}{flag} | {desc} |"


HEAD = "| repo | stars | license | language | last push | description |\n|---|---|---|---|---|---|"


def main() -> None:
    print(f"# GitHub survey data\n\nGenerated {datetime.date.today()} by `scripts/research/github_survey.py`. "
          "Search results are ranked by stars; `none` means GitHub found no license file, which means *all rights "
          "reserved* and the code cannot be reused.\n")
    seen: set[str] = set()
    for q in QUERIES:
        print(f"## Search: `{q}`\n")
        try:
            items = get("https://api.github.com/search/repositories?" + urllib.parse.urlencode(
                {"q": q, "sort": "stars", "per_page": 8}))["items"]
        except Exception as exc:                         # rate limit / network: record it, keep going
            print(f"_query failed: {exc}_\n")
            time.sleep(10)
            continue
        fresh = [r for r in items if r["full_name"] not in seen]
        seen.update(r["full_name"] for r in items)
        print(HEAD if fresh else "_no new results_")
        for r in fresh:
            print(row(r))
        print()
        time.sleep(7)
    print("## Inspected individually\n\n" + HEAD)
    for name in INSPECT:
        try:
            print(row(get("https://api.github.com/repos/" + name)))
        except Exception as exc:
            print(f"| {name} | | | | | lookup failed: {exc} |")
        time.sleep(1)
    print("\n## Repo root listing check for unlicensed candidates\n")
    for name in ("Kimbatt/torrent-creator",):
        files = [f["name"] for f in get(f"https://api.github.com/repos/{name}/contents/")]
        has = [f for f in files if f.upper().startswith(("LICENSE", "COPYING", "UNLICENSE"))]
        print(f"- {name}: {'license file: ' + ', '.join(has) if has else 'no LICENSE/COPYING file in the repository root'}")


if __name__ == "__main__":
    main()
