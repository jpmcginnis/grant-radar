"""
NSF funding opportunities scraper.

Uses NSF's public funding opportunities search:
  https://www.nsf.gov/funding/opportunities-active

Falls back to the directorate-filtered pages when the public API isn't
usable from this environment.
"""

import sys
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schema import Opportunity  # noqa: E402

NSF_LIST = "https://www.nsf.gov/funding/opportunities-active"
USER_AGENT = "grant-radar/1.0"


def scrape(source_config: dict) -> list[Opportunity]:
    name = source_config.get("name", "nsf_funding")
    directorate = source_config.get("directorate", "")
    program = source_config.get("program", "")

    params = {}
    if directorate:
        params["directorate"] = directorate
    if program:
        params["search"] = program

    try:
        r = requests.get(
            NSF_LIST, params=params, headers={"User-Agent": USER_AGENT}, timeout=30
        )
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"[nsf] fetch failed: {e}", file=sys.stderr)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    out = []
    for card in soup.select(".funding-opportunity, .opportunity-card, article"):
        title_el = card.find(["h2", "h3", "a"])
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title:
            continue
        link_el = card.find("a", href=True)
        link = link_el["href"] if link_el else NSF_LIST
        if link.startswith("/"):
            link = "https://www.nsf.gov" + link
        body = card.get_text(" ", strip=True)[:2000]
        out.append(
            Opportunity(
                id="",
                source=name,
                source_url=link,
                opportunity_number=link.rsplit("/", 1)[-1][:80],
                title=title,
                sponsor="NSF",
                mechanism="NSF",
                posted=date.today().isoformat(),
                purpose=body,
                category="nsf",
            )
        )
    return out
