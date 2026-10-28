"""
Unified opportunity schema. Every scraper normalizes to this shape.
JSON-serializable; the dashboard reads these directly.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from typing import Optional
import hashlib
import json


@dataclass
class Opportunity:
    # Identity
    id: str                        # stable hash of source + opportunity_number
    source: str                    # e.g. "nih_guide_all"
    source_url: str                # link to the full solicitation
    opportunity_number: str        # NIH FOA (e.g. PA-23-271) or foundation program name

    # Human-readable
    title: str
    sponsor: str                   # NIH IC, foundation name, agency
    mechanism: str                 # R01, K08, Innovation Award, etc.

    # Dates (ISO 8601 strings for JSON portability)
    loi_due: Optional[str] = None
    app_due: Optional[str] = None
    posted: Optional[str] = None
    expires: Optional[str] = None

    # Content
    purpose: str = ""              # short description
    eligibility_summary: str = ""
    budget_summary: str = ""       # "Up to $250k direct/yr for 5 yrs"

    # Scraper metadata
    first_seen: str = field(default_factory=lambda: date.today().isoformat())
    last_seen: str = field(default_factory=lambda: date.today().isoformat())
    raw_html_hash: Optional[str] = None

    # Classification (filled by scorer)
    category: str = ""             # nih | foundation | dod | nsf | arpa_h
    bucket: str = ""               # early_career_k | r_mechanism | private_innovation | federal_other
    fit_score: float = 0.0
    fit_rationale: str = ""
    matched_pillars: list = field(default_factory=list)

    # User state (persisted across runs)
    status: str = "new"            # new | interested | drafting | submitted | declined | dismissed
    user_notes: str = ""

    # Draft content
    aims_skeleton: Optional[str] = None

    def __post_init__(self):
        if not self.id:
            self.id = self.compute_id()

    def compute_id(self) -> str:
        key = f"{self.source}::{self.opportunity_number}::{self.title}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Opportunity":
        return cls(**d)


def save_opportunities(opportunities: list, path: str) -> None:
    """Persist to JSON, merging with existing records to preserve user state."""
    try:
        with open(path) as f:
            existing = {o["id"]: o for o in json.load(f)}
    except (FileNotFoundError, json.JSONDecodeError):
        existing = {}

    today = date.today().isoformat()

    for opp in opportunities:
        d = opp.to_dict() if isinstance(opp, Opportunity) else opp
        if d["id"] in existing:
            prev = existing[d["id"]]
            # Preserve user state and first_seen
            d["status"] = prev.get("status", "new")
            d["user_notes"] = prev.get("user_notes", "")
            d["first_seen"] = prev.get("first_seen", today)
            d["last_seen"] = today
        existing[d["id"]] = d

    with open(path, "w") as f:
        json.dump(list(existing.values()), f, indent=2, default=str)


def load_opportunities(path: str) -> list:
    try:
        with open(path) as f:
            return [Opportunity.from_dict(d) for d in json.load(f)]
    except (FileNotFoundError, json.JSONDecodeError):
        return []
