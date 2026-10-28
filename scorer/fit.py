"""
Fit scorer. Compares each opportunity's text against JP's research profile
and emits a 0-100 score plus a rationale.

Rubric (max 100):
  Pillar coverage       — 50 pts (sum of weights of matched primary pillars,
                                  capped and rescaled)
  Mechanism fit         — 20 pts (right career stage / activity code)
  Deadline runway       — 15 pts (enough lead time to actually apply)
  Budget appropriateness— 10 pts (within configured floor/ceiling)
  Eligibility hits      —  5 pts (physician-scientist, early-career cues)
"""

import re
from datetime import date
from pathlib import Path

import yaml

PROFILE_PATH = Path(__file__).resolve().parent.parent / "profile.yaml"


def _load_profile() -> dict:
    with open(PROFILE_PATH) as f:
        return yaml.safe_load(f)


_PROFILE = _load_profile()


def _text_of(opp) -> str:
    d = opp if isinstance(opp, dict) else opp.to_dict()
    return " ".join(
        str(d.get(k, ""))
        for k in ("title", "purpose", "eligibility_summary", "mechanism", "sponsor")
    ).lower()


def _pillar_score(text: str) -> tuple[float, list[str]]:
    max_raw = sum(p["weight"] for p in _PROFILE["research_pillars"]["primary"])
    matched_weight = 0
    matched_names = []
    for pillar in _PROFILE["research_pillars"]["primary"]:
        if any(re.search(r"\b" + re.escape(kw.lower()) + r"\b", text) for kw in pillar["keywords"]):
            matched_weight += pillar["weight"]
            matched_names.append(pillar["name"])
    # Secondary pillars get half credit
    for pillar in _PROFILE["research_pillars"]["secondary"]:
        if any(re.search(r"\b" + re.escape(kw.lower()) + r"\b", text) for kw in pillar["keywords"]):
            matched_weight += pillar["weight"] * 0.5
            matched_names.append(f"{pillar['name']} (secondary)")
    pts = min(50.0, 50.0 * matched_weight / max_raw) if max_raw else 0.0
    return pts, matched_names


def _mechanism_score(opp) -> float:
    d = opp if isinstance(opp, dict) else opp.to_dict()
    mech = (d.get("mechanism") or "").upper()
    bucket_cfg = {
        "early_career_k": ["K08", "K22", "K99", "K23", "K01", "K25", "R00"],
        "r_mechanisms": ["R01", "R21", "R03", "R35", "R37", "DP1", "DP2", "DP5"],
        "foundation": ["FOUNDATION"],
        "dod": ["CDMRP", "DOD"],
        "nsf": ["NSF"],
        "arpa_h": ["ARPA-H", "ARPAH"],
    }
    for bucket, codes in bucket_cfg.items():
        if any(c in mech for c in codes):
            # Early-career K and physician-scientist buckets score highest
            if bucket in ("early_career_k", "foundation"):
                return 20.0
            if bucket in ("r_mechanisms", "arpa_h"):
                return 16.0
            return 12.0
    # Unknown mechanism — give partial credit
    return 8.0


def _runway_score(opp) -> float:
    d = opp if isinstance(opp, dict) else opp.to_dict()
    due = d.get("loi_due") or d.get("app_due")
    if not due:
        return 10.0  # unknown deadline — assume rolling
    try:
        due_date = date.fromisoformat(due)
    except ValueError:
        return 10.0
    days = (due_date - date.today()).days
    if days < 0:
        return 0.0
    if days < 14:
        return 3.0  # too tight
    if days < 45:
        return 10.0  # usable but hustle
    if days < 180:
        return 15.0  # ideal runway
    return 12.0  # far-off, lower urgency


def _budget_score(opp) -> float:
    d = opp if isinstance(opp, dict) else opp.to_dict()
    text = (d.get("budget_summary") or "") + " " + (d.get("purpose") or "")
    amounts = []
    for m in re.finditer(r"\$([\d,]+)(?:\s*(million|M|K|thousand))?", text, re.I):
        n = int(m.group(1).replace(",", ""))
        suffix = (m.group(2) or "").lower()
        if suffix in ("million", "m"):
            n *= 1_000_000
        elif suffix in ("thousand", "k"):
            n *= 1_000
        amounts.append(n)
    if not amounts:
        return 7.0  # neutral
    biggest = max(amounts)
    floor = _PROFILE["preferences"]["budget_floor_usd"]
    ceiling = _PROFILE["preferences"]["budget_ceiling_usd"]
    if biggest < floor:
        return 2.0
    if biggest > ceiling:
        return 6.0
    return 10.0


def _eligibility_score(opp) -> float:
    d = opp if isinstance(opp, dict) else opp.to_dict()
    text = (d.get("eligibility_summary") or "") + " " + (d.get("purpose") or "")
    text = text.lower()
    pts = 0.0
    cues = {
        "physician-scientist": 2.0,
        "physician scientist": 2.0,
        "md/phd": 1.5,
        "md-phd": 1.5,
        "early-career": 1.5,
        "early career": 1.5,
        "new investigator": 1.5,
        "early-stage": 1.5,
        "junior faculty": 1.5,
        "instructor": 1.0,
        "clinician": 1.0,
    }
    for cue, w in cues.items():
        if cue in text:
            pts += w
    return min(5.0, pts) if pts else 2.5


def bucket_for(opp) -> str:
    d = opp if isinstance(opp, dict) else opp.to_dict()
    mech = (d.get("mechanism") or "").upper()
    cat = d.get("category", "")

    if any(c in mech for c in ["K08", "K22", "K99", "K23", "K01", "K25", "R00"]):
        return "early_career_k"
    if any(c in mech for c in ["R01", "R21", "R03", "R35", "R37", "DP1", "DP2", "DP5"]):
        return "r_mechanism"
    if cat == "foundation":
        return "private_innovation"
    if cat in ("dod", "nsf", "arpa_h"):
        return "federal_other"
    return "other"


def score_opportunity(opp) -> tuple[float, str, list[str], str]:
    """Return (score, rationale, matched_pillars, bucket)."""
    text = _text_of(opp)
    pillar_pts, matched = _pillar_score(text)
    mech_pts = _mechanism_score(opp)
    runway_pts = _runway_score(opp)
    budget_pts = _budget_score(opp)
    elig_pts = _eligibility_score(opp)

    total = pillar_pts + mech_pts + runway_pts + budget_pts + elig_pts
    rationale = (
        f"pillars {pillar_pts:.0f}/50 "
        f"({', '.join(matched[:3]) or 'no primary matches'}) · "
        f"mechanism {mech_pts:.0f}/20 · "
        f"runway {runway_pts:.0f}/15 · "
        f"budget {budget_pts:.0f}/10 · "
        f"eligibility {elig_pts:.0f}/5"
    )
    return round(total, 1), rationale, matched, bucket_for(opp)
