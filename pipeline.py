"""
Main pipeline. Called weekly by GitHub Actions.

Steps:
  1. Load sources.yaml
  2. Dispatch to each scraper
  3. Score every opportunity
  4. Attach aims-skeletons to the top 3 new ones
  5. Persist to data/opportunities.json (merging with prior state)
  6. Write site/data/opportunities.json (the dashboard reads this)
  7. Write drafts/<id>.md for each aims-skeleton
  8. Emit site/data/digest.json for the email job

Run locally:
    python pipeline.py --once --limit 5
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from schema import Opportunity, save_opportunities, load_opportunities  # noqa: E402
from scrapers import get_scraper  # noqa: E402
from scorer import score_opportunity, generate_aims_skeleton  # noqa: E402


DATA_DIR = ROOT / "data"
SITE_DATA = ROOT / "site" / "data"
DRAFTS_DIR = ROOT / "drafts"
DATA_DIR.mkdir(exist_ok=True)
SITE_DATA.mkdir(parents=True, exist_ok=True)
DRAFTS_DIR.mkdir(exist_ok=True)

OPPS_PATH = DATA_DIR / "opportunities.json"
SITE_OPPS = SITE_DATA / "opportunities.json"
DIGEST_PATH = SITE_DATA / "digest.json"


def load_sources() -> list[dict]:
    with open(ROOT / "sources.yaml") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("sources", [])


def run_scrapers(sources: list[dict], only: str | None = None) -> list[Opportunity]:
    all_opps: list[Opportunity] = []
    for src in sources:
        if only and src["name"] != only:
            continue
        scraper = get_scraper(src["scraper"])
        print(f"[pipeline] running {src['name']} ({src['scraper']})", file=sys.stderr)
        try:
            opps = scraper(src)
            print(f"[pipeline]   → {len(opps)} opportunities", file=sys.stderr)
            all_opps.extend(opps)
        except Exception as e:  # noqa: BLE001
            print(f"[pipeline]   ! failed: {e}", file=sys.stderr)
    return all_opps


def score_all(opps: list[Opportunity]) -> list[Opportunity]:
    for opp in opps:
        score, rationale, matched, bucket = score_opportunity(opp)
        opp.fit_score = score
        opp.fit_rationale = rationale
        opp.matched_pillars = matched
        opp.bucket = bucket
    return opps


def attach_aims_to_top(opps: list[Opportunity], prior_ids: set[str], top_n: int = 3) -> None:
    """Attach a skeleton to the top N *new* opportunities only."""
    new_opps = [o for o in opps if o.id not in prior_ids]
    new_opps.sort(key=lambda o: o.fit_score, reverse=True)
    for opp in new_opps[:top_n]:
        skeleton = generate_aims_skeleton(opp)
        opp.aims_skeleton = skeleton
        draft_path = DRAFTS_DIR / f"{opp.id}.md"
        draft_path.write_text(
            f"# {opp.title}\n\n"
            f"**Sponsor:** {opp.sponsor}  \n"
            f"**Mechanism:** {opp.mechanism}  \n"
            f"**Fit score:** {opp.fit_score}/100  \n"
            f"**Source:** <{opp.source_url}>  \n"
            f"**LOI due:** {opp.loi_due or '—'}  \n"
            f"**App due:** {opp.app_due or '—'}  \n\n"
            f"---\n\n"
            f"{skeleton}\n"
        )


def write_digest(opps: list[Opportunity], prior_ids: set[str]) -> dict:
    today = date.today()
    new_opps = [o for o in opps if o.id not in prior_ids]
    new_opps.sort(key=lambda o: o.fit_score, reverse=True)

    def _summarize(o):
        return {
            "id": o.id,
            "title": o.title,
            "sponsor": o.sponsor,
            "mechanism": o.mechanism,
            "fit_score": o.fit_score,
            "fit_rationale": o.fit_rationale,
            "loi_due": o.loi_due,
            "app_due": o.app_due,
            "source_url": o.source_url,
            "has_aims": bool(o.aims_skeleton),
        }

    # Upcoming deadlines across ALL opps (not just new)
    upcoming = []
    for o in opps:
        due = o.loi_due or o.app_due
        if not due:
            continue
        try:
            dd = date.fromisoformat(due)
        except ValueError:
            continue
        if (dd - today).days < 0 or (dd - today).days > 120:
            continue
        upcoming.append({
            "id": o.id,
            "title": o.title,
            "sponsor": o.sponsor,
            "due": due,
            "due_kind": "LOI" if o.loi_due == due else "App",
            "days_out": (dd - today).days,
            "fit_score": o.fit_score,
            "source_url": o.source_url,
        })
    upcoming.sort(key=lambda x: x["days_out"])

    digest = {
        "generated": today.isoformat(),
        "new_this_week": [_summarize(o) for o in new_opps[:10]],
        "top_three": [_summarize(o) for o in new_opps[:3]],
        "upcoming_deadlines": upcoming[:15],
        "total_tracked": len(opps),
        "new_count": len(new_opps),
    }
    DIGEST_PATH.write_text(json.dumps(digest, indent=2))
    return digest


def main() -> int:
    parser = argparse.ArgumentParser(description="Grant radar weekly pipeline")
    parser.add_argument("--only", help="Run just one named source")
    parser.add_argument("--limit", type=int, help="Keep only the first N opportunities")
    parser.add_argument("--dry-run", action="store_true", help="Don't write files")
    args = parser.parse_args()

    prior = load_opportunities(str(OPPS_PATH))
    prior_ids = {o.id for o in prior}

    sources = load_sources()
    scraped = run_scrapers(sources, only=args.only)
    if args.limit:
        scraped = scraped[: args.limit]

    scored = score_all(scraped)
    attach_aims_to_top(scored, prior_ids, top_n=3)

    if args.dry_run:
        print(json.dumps([o.to_dict() for o in scored[:3]], indent=2, default=str))
        return 0

    save_opportunities(scored, str(OPPS_PATH))
    # Mirror into the site data directory for the dashboard
    with open(OPPS_PATH) as f, open(SITE_OPPS, "w") as g:
        g.write(f.read())

    all_opps = load_opportunities(str(OPPS_PATH))
    digest = write_digest(all_opps, prior_ids)

    print(
        f"[pipeline] done. {digest['new_count']} new, "
        f"{digest['total_tracked']} total tracked. "
        f"Top new fit: {digest['top_three'][0]['fit_score'] if digest['top_three'] else 'n/a'}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
