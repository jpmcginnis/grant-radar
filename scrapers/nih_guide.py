"""
NIH Guide for Grants and Contracts scraper.

Pulls the NIH Guide RSS feed and the search API, filters by activity code,
and normalizes to the Opportunity schema.

NIH exposes:
  - RSS: https://grants.nih.gov/grants/guide/WeeklyIndexRSS.cfm
  - Search: https://search.grants.nih.gov/guide/api/data (returns JSON)
"""

import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schema import Opportunity  # noqa: E402


NIH_SEARCH_API = "https://search.grants.nih.gov/guide/api/data"
NIH_GUIDE_RSS = "https://grants.nih.gov/grants/guide/WeeklyIndexRSS.cfm"

USER_AGENT = "grant-radar/1.0 (research pipeline for JP McGinnis, BCM)"


def _fetch_json(params: dict, timeout: int = 30) -> dict:
    r = requests.get(
        NIH_SEARCH_API,
        params=params,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()


def _parse_date(s: str | None) -> str | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%B %d, %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date().isoformat()
        except (ValueError, AttributeError):
            continue
    return None


def _opportunities_from_api(records: Iterable[dict], source_name: str) -> list[Opportunity]:
    out = []
    for rec in records:
        foa = rec.get("docnum") or rec.get("foa") or rec.get("number", "")
        title = rec.get("title") or rec.get("doctitle", "")
        if not foa or not title:
            continue

        url = rec.get("url") or f"https://grants.nih.gov/grants/guide/pa-files/{foa}.html"

        activity = rec.get("activity_code") or _extract_activity(foa)
        ic = ", ".join(rec.get("participating_orgs", [])) or rec.get("primary_ic", "NIH")

        opp = Opportunity(
            id="",
            source=source_name,
            source_url=url,
            opportunity_number=foa,
            title=title.strip(),
            sponsor=ic,
            mechanism=activity or "NIH",
            loi_due=_parse_date(rec.get("loi_date")),
            app_due=_parse_date(rec.get("app_due_date") or rec.get("expiration_date")),
            posted=_parse_date(rec.get("release_date") or rec.get("posted_date")),
            expires=_parse_date(rec.get("expiration_date")),
            purpose=(rec.get("purpose") or rec.get("description", ""))[:2000],
            eligibility_summary=rec.get("eligibility", "")[:500],
            budget_summary=rec.get("award_info", "")[:300],
            category="nih",
        )
        out.append(opp)
    return out


def _extract_activity(foa: str) -> str:
    m = re.search(r"(?:PA|PAR|PAS|RFA|NOT)-\w{2}-\d{2}-\d{3,}", foa)
    if m:
        # Try to pull activity from a parenthetical if present elsewhere
        return foa.split("-")[0] if "-" in foa else foa
    return ""


def _fetch_rss_fallback(activity_codes: list[str]) -> list[Opportunity]:
    """Fallback when the JSON API isn't reachable."""
    r = requests.get(NIH_GUIDE_RSS, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "xml")
    out = []
    code_pattern = re.compile(r"\((" + "|".join(activity_codes) + r")\)", re.I)
    for item in soup.find_all("item"):
        title = (item.title.text if item.title else "").strip()
        if not code_pattern.search(title):
            continue
        link = (item.link.text if item.link else "").strip()
        desc = (item.description.text if item.description else "").strip()
        pub = _parse_date(item.pubDate.text if item.pubDate else None)
        foa_match = re.search(r"(PA|PAR|PAS|RFA|NOT)-\w{2}-\d{2}-\d{3,}", title + " " + desc)
        foa = foa_match.group(0) if foa_match else link.rsplit("/", 1)[-1].replace(".html", "")
        activity_match = code_pattern.search(title)
        activity = activity_match.group(1).upper() if activity_match else "NIH"
        out.append(
            Opportunity(
                id="",
                source="nih_guide_rss",
                source_url=link,
                opportunity_number=foa,
                title=title,
                sponsor="NIH",
                mechanism=activity,
                posted=pub,
                purpose=desc[:2000],
                category="nih",
            )
        )
    return out


def scrape(source_config: dict) -> list[Opportunity]:
    activity_codes = source_config.get("activity_codes", [])
    source_name = source_config.get("name", "nih_guide")

    all_opps: list[Opportunity] = []

    # Try the JSON API first, one query per activity code
    try:
        for code in activity_codes:
            params = {
                "query": code,
                "activity_code": code,
                "max": 200,
                "sort": "release_date desc",
            }
            data = _fetch_json(params)
            records = data.get("docs") or data.get("results") or []
            all_opps.extend(_opportunities_from_api(records, source_name))
    except (requests.RequestException, ValueError) as e:
        print(f"[nih_guide] API path failed ({e}); falling back to RSS", file=sys.stderr)
        all_opps = _fetch_rss_fallback(activity_codes)

    # Dedupe by opportunity_number
    seen = {}
    for o in all_opps:
        seen[o.opportunity_number] = o
    return list(seen.values())
