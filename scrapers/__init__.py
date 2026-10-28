"""Scraper package. Each module exposes a scrape(source_config) -> list[Opportunity]."""

from .nih_guide import scrape as scrape_nih_guide
from .nih_reporter import scrape as scrape_nih_reporter
from .html_generic import scrape as scrape_html_generic
from .nsf_funding import scrape as scrape_nsf_funding

SCRAPERS = {
    "nih_guide": scrape_nih_guide,
    "nih_reporter": scrape_nih_reporter,
    "html_generic": scrape_html_generic,
    "nsf_funding": scrape_nsf_funding,
}


def get_scraper(name: str):
    if name not in SCRAPERS:
        raise ValueError(f"Unknown scraper: {name}. Available: {list(SCRAPERS)}")
    return SCRAPERS[name]
