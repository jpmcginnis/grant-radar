"""
NIH RePORTER scraper.

RePORTER lists funded projects, not open opportunities, but it is the single
best signal for which study sections and ICs are funding your space.
The radar surfaces these as "fundable neighborhood" items with lower weight.

API: https://api.reporter.nih.gov/v2/projects/search  (POST, JSON body)
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schema import Opportunity  # noqa: E402

REPORTER_URL = "https://api.reporter.nih.gov/v2/projects/search"
USER_AGENT = "grant-radar/1.0"


def scrape(source_config: dict) -> list[Opportunity]:
    terms = source_config.get("terms", [])
    name = source_config.get("name", "nih_reporter")
    today = date.today()
    cutoff = (today - timedelta(days=365)).isoformat()

    results: list[Opportunity] = []
    for term in terms:
        body = {
            "criteria": {
                "advanced_text_search": {
                    "operator": "and",
                    "search_field": "projecttitle,abstracttext,terms",
                    "search_text": term,
                },
                "project_start_date": {"from_date": cutoff, "to_date": today.isoformat()},
            },
            "include_fields": [
                "ProjectNum",
                "ProjectTitle",
                "AbstractText",
                "ContactPiName",
                "Organization",
                "AgencyIcAdmin",
                "ProjectStartDate",
                "ProjectEndDate",
                "AwardAmount",
                "ActivityCode",
            ],
            "offset": 0,
            "limit": 50,
            "sort_field": "project_start_date",
            "sort_order": "desc",
        }
        try:
            r = requests.post(
                REPORTER_URL,
                json=body,
                headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, ValueError) as e:
            print(f"[nih_reporter] query {term!r} failed: {e}", file=sys.stderr)
            continue

        for rec in data.get("results", []):
            activity = rec.get("activity_code") or ""
            proj_num = rec.get("project_num", "")
            title = (rec.get("project_title") or "").strip()
            if not proj_num or not title:
                continue
            agency = (rec.get("agency_ic_admin") or {}).get("name", "NIH")
            amount = rec.get("award_amount")
            pi = (rec.get("contact_pi_name") or "").strip()
            org = (rec.get("organization") or {}).get("org_name", "")

            results.append(
                Opportunity(
                    id="",
                    source=name,
                    source_url=f"https://reporter.nih.gov/project-details/{proj_num}",
                    opportunity_number=proj_num,
                    title=f"[Funded ref] {title}",
                    sponsor=agency,
                    mechanism=activity or "NIH",
                    posted=rec.get("project_start_date", "")[:10] or None,
                    expires=rec.get("project_end_date", "")[:10] or None,
                    purpose=(rec.get("abstract_text") or "")[:1500],
                    budget_summary=f"${amount:,} total" if amount else "",
                    eligibility_summary=f"PI: {pi} ({org})" if pi else "",
                    category="nih_funded_ref",
                )
            )
    return results
