"""
Generic HTML scraper for foundation pages.

Foundation pages vary wildly, so this scraper is intentionally lossy:
it pulls the full visible text, extracts anything that looks like a deadline
or an award amount, and leaves the fit-scoring + aims-skeleton generator
to make sense of it. The URL is always captured so the user can click through.

For higher-fidelity extraction, add a per-source parser in scrapers/foundations/
and dispatch to it here.
"""

import re
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schema import Opportunity  # noqa: E402

USER_AGENT = (
    "Mozilla/5.0 (compatible; grant-radar/1.0; +https://github.com/jpmcginnis1/grant-radar)"
)

DATE_PATTERNS = [
    # "December 1, 2026" / "Dec 1, 2026"
    (
        re.compile(
            r"(January|February|March|April|May|June|July|August|September|"
            r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+"
            r"(\d{1,2}),?\s+(\d{4})",
            re.I,
        ),
        "%B %d %Y",
    ),
    # 2026-12-01 / 2026/12/01
    (re.compile(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})"), "%Y-%m-%d"),
    # 12/1/2026
    (re.compile(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})"), "%m/%d/%Y"),
]

DEADLINE_CUE = re.compile(
    r"(deadline|due\s+by|due\s+date|submission|applications?\s+due|"
    r"LOI\s+due|letter\s+of\s+intent|closes?|open\s+until)",
    re.I,
)
LOI_CUE = re.compile(r"(LOI|letter\s+of\s+intent|pre[-\s]?application)", re.I)
BUDGET_CUE = re.compile(r"\$[\d,]+(?:\.\d+)?(?:\s*(?:million|M|K|thousand))?", re.I)


def _slugify(url: str) -> str:
    parsed = urlparse(url)
    return (parsed.netloc + parsed.path).strip("/").replace("/", "-")[:80]


def _parse_date_in_context(text: str) -> str | None:
    for pat, fmt in DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        try:
            raw = " ".join(m.groups())
            # normalize month abbreviations
            dt = None
            for try_fmt in (
                fmt,
                "%b %d %Y",
                "%B %d %Y",
                "%B %d, %Y",
                "%b %d, %Y",
            ):
                try:
                    dt = datetime.strptime(raw.replace(".", "").replace(",", ""), try_fmt)
                    break
                except ValueError:
                    continue
            if not dt:
                continue
            # Only accept future-ish dates (not something from 1998)
            if dt.year < date.today().year - 1:
                continue
            return dt.date().isoformat()
        except (ValueError, IndexError):
            continue
    return None


def _find_deadlines(text: str) -> tuple[str | None, str | None]:
    """Return (loi_due, app_due) best-effort."""
    loi, app = None, None
    for line in text.splitlines():
        line = line.strip()
        if not line or len(line) > 400:
            continue
        if DEADLINE_CUE.search(line):
            d = _parse_date_in_context(line)
            if not d:
                continue
            if LOI_CUE.search(line) and not loi:
                loi = d
            elif not app:
                app = d
    return loi, app


def _find_budget(text: str) -> str:
    hits = BUDGET_CUE.findall(text)
    if not hits:
        return ""
    # Return the first few distinct money mentions
    seen = []
    for h in hits:
        if h not in seen:
            seen.append(h)
        if len(seen) >= 3:
            break
    return " / ".join(seen)


def _find_programs(soup: BeautifulSoup) -> list[tuple[str, str]]:
    """
    Pull candidate program blocks from the page.
    A 'program' is anything that looks like a named award on this page.
    We take headings (h1/h2/h3) and their immediate text block as the unit.
    """
    programs = []
    for heading in soup.find_all(["h1", "h2", "h3"]):
        title = heading.get_text(strip=True)
        if not title or len(title) < 4 or len(title) > 200:
            continue
        # Skip obvious nav/boilerplate
        if title.lower() in {"menu", "search", "home", "about", "contact"}:
            continue
        # Collect text until next heading
        body = []
        for sib in heading.find_next_siblings():
            if sib.name in {"h1", "h2", "h3"}:
                break
            body.append(sib.get_text(" ", strip=True))
        programs.append((title, "\n".join(body)[:3000]))
    return programs


def scrape(source_config: dict) -> list[Opportunity]:
    url = source_config["url"]
    name = source_config.get("name", _slugify(url))
    sponsor = source_config.get("sponsor") or _infer_sponsor(url)

    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"[html_generic] {url} failed: {e}", file=sys.stderr)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    # Strip boilerplate
    for tag in soup(["script", "style", "nav", "footer", "header", "form"]):
        tag.decompose()

    programs = _find_programs(soup)

    if not programs:
        # Fall back to a single page-level opportunity
        page_text = soup.get_text("\n", strip=True)[:5000]
        loi, app = _find_deadlines(page_text)
        return [
            Opportunity(
                id="",
                source=name,
                source_url=url,
                opportunity_number=_slugify(url),
                title=soup.title.get_text(strip=True) if soup.title else name,
                sponsor=sponsor,
                mechanism="Foundation",
                loi_due=loi,
                app_due=app,
                posted=date.today().isoformat(),
                purpose=page_text[:2000],
                budget_summary=_find_budget(page_text),
                category=source_config.get("category", "foundation"),
            )
        ]

    out = []
    for title, body in programs:
        loi, app = _find_deadlines(body)
        out.append(
            Opportunity(
                id="",
                source=name,
                source_url=url,
                opportunity_number=f"{_slugify(url)}::{title[:60]}",
                title=title,
                sponsor=sponsor,
                mechanism="Foundation",
                loi_due=loi,
                app_due=app,
                posted=date.today().isoformat(),
                purpose=body[:2000],
                budget_summary=_find_budget(body),
                category=source_config.get("category", "foundation"),
            )
        )
    return out


def _infer_sponsor(url: str) -> str:
    host = urlparse(url).netloc.lower().replace("www.", "")
    mapping = {
        "damonrunyon.org": "Damon Runyon Cancer Research Foundation",
        "searlescholars.net": "Searle Scholars Program",
        "pewtrusts.org": "Pew Charitable Trusts",
        "bwfund.org": "Burroughs Wellcome Fund",
        "dorisduke.org": "Doris Duke Charitable Foundation",
        "mcknight.org": "McKnight Endowment Fund",
        "sloan.org": "Alfred P. Sloan Foundation",
        "alleninstitute.org": "Allen Institute / Paul G. Allen Frontiers Group",
        "dana.org": "Dana Foundation",
        "thebrf.org": "Brain Research Foundation",
        "thehartwellfoundation.org": "Hartwell Foundation",
        "whitehall.org": "Whitehall Foundation",
        "cdmrp.health.mil": "DoD CDMRP",
        "arpa-h.gov": "ARPA-H",
        "chanzuckerberg.com": "Chan Zuckerberg Initiative",
    }
    return mapping.get(host, host)
