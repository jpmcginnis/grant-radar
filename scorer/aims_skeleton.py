"""
Aims skeleton generator.

Deterministic templating that fills a Specific Aims scaffold using:
  - the opportunity's text (mechanism, purpose, keywords)
  - JP's pillar library

The goal is a *starting point* — three draft aims that cover platform,
discovery, and translational handoff, with language tuned to the mechanism.
It intentionally does NOT invent preliminary data. It leaves <PRELIM> and
<SAMPLE> tags for JP to fill in.

For LLM-generated prose, set the environment variable
GRANT_RADAR_LLM_PROVIDER=anthropic (or openai) and the generator will fan
out to that service. By default it runs offline with the template.
"""

import os
import re
import textwrap
from pathlib import Path

import yaml

PROFILE_PATH = Path(__file__).resolve().parent.parent / "profile.yaml"


def _profile() -> dict:
    with open(PROFILE_PATH) as f:
        return yaml.safe_load(f)


def _detect_focus(opp_text: str, pillars: list[dict]) -> list[dict]:
    text = opp_text.lower()
    hits = []
    for p in pillars:
        if any(re.search(r"\b" + re.escape(kw.lower()) + r"\b", text) for kw in p["keywords"]):
            hits.append(p)
    return hits


def _template_aims(opp: dict, matched_pillars: list[dict]) -> str:
    title = opp.get("title", "")
    mech = opp.get("mechanism", "")
    sponsor = opp.get("sponsor", "")

    # Pick the dominant pillar(s)
    primary = matched_pillars[0] if matched_pillars else {
        "name": "Human ex vivo brain slice platform",
        "keywords": ["ex vivo", "brain slice"],
    }
    secondary = matched_pillars[1] if len(matched_pillars) > 1 else {
        "name": "AAV capsid and enhancer engineering",
        "keywords": ["AAV", "enhancer"],
    }

    skeleton = f"""\
    DRAFT SPECIFIC AIMS — {mech} / {sponsor}
    Mapped against: {title}

    OVERVIEW (1 paragraph to write)
    ─────────────────────────────────
    Problem framing: CNS gene therapy has been bottlenecked by (a) the
    absence of human substrates for pre-clinical delivery screening and
    (b) the gap between model systems (iPSC, mouse, NHP) and the human
    cortex that drugs ultimately target. Our ex vivo human brain slice
    culture platform addresses this gap directly by using surgically
    resected tissue to screen AAV capsid and enhancer libraries at the
    cellular resolution of the human brain. <PRELIM: 2-3 sentences on
    our preliminary dataset — number of specimens, viability window,
    library size screened, headline hits.>

    AIM 1 — Platform / infrastructure
    ─────────────────────────────────
    Rationale: {primary['name']} as a reproducible substrate for library
    screening requires characterizing fidelity, viability, and
    inter-specimen variance.

    1a. Benchmark slice viability and transcriptional fidelity across
        <SAMPLE: n specimens from m anatomical regions> at D0, D7, D14
        using snRNA-seq + snATAC-seq, with comparison to matched acute
        dissociations.
    1b. Define the operational window — which cell types remain
        transcriptionally stable, which drift — and lock the SOP for
        downstream library screens.
    1c. Deliverable: a public resource (data + SOPs) that other labs
        can adopt.

    AIM 2 — Discovery
    ─────────────────
    Rationale: {secondary['name']} benefits directly from screening in
    the real target substrate.

    2a. Apply our barcoded AAV capsid library (n = <PRELIM: library
        size>) to slices from <SAMPLE> and recover
        capsid-by-cell-type tropism matrices via scRNA-seq.
    2b. Apply the enhancer library in parallel and identify
        cell-type-restricted drivers for <TARGET CELL TYPES — e.g.,
        L5 ET neurons, inhibitory PV interneurons, microglia>.
    2c. Validate the top <N> hits with single-vector in situ
        experiments.

    AIM 3 — Translational handoff
    ──────────────────────────────
    Rationale: a platform earns its keep by producing substrates for
    others. This aim turns Aim 2's hits into a shareable toolkit.

    3a. Package the top capsid × enhancer combinations as a public AAV
        catalog with vector maps, titers, and expression data.
    3b. Pilot one combination in a disease-relevant assay — <CHOICE:
        human AVM tissue, epileptic cortex, GBM resection margin> —
        to show line-of-sight to clinical relevance.
    3c. Deliverable: shared vectors + data at <REPOSITORY> within year
        <N> of the award.

    INVESTIGATOR / ENVIRONMENT
    ──────────────────────────
    JP McGinnis, MD PhD, is uniquely positioned at the intersection of
    operative neurosurgery and vector biology: direct, same-day access
    to human CNS tissue; established computational pipeline (published
    atlas, snATAC harmonization preprint); existing collaborations with
    [Allen Institute, Deliverome/Radial, Parallel Squared]; independent
    faculty appointment at BCM July 2027.

    REVIEWER-FACING NOTES — things to pre-empt
    ──────────────────────────────────────────
    - "Why ex vivo and not iPSC organoids?" <ANSWER>
    - "Specimen variability as a confound" <ANSWER + 1a data>
    - "Scalability of surgical specimen pipeline" <ANSWER: ongoing OR
      case volume, existing consent IRB>
    - "Translation path given ex vivo starting point" <ANSWER: Aim 3>
    """
    return textwrap.dedent(skeleton)


def _llm_aims(opp: dict, matched_pillars: list[dict]) -> str | None:
    """Optional: call an LLM for richer prose. No-op if no provider set."""
    provider = os.environ.get("GRANT_RADAR_LLM_PROVIDER")
    if not provider:
        return None
    # Intentionally a stub — the GitHub Action can set this via Claude Code
    # or an Anthropic API key. Returning None falls back to the template.
    return None


def generate_aims_skeleton(opp) -> str:
    d = opp if isinstance(opp, dict) else opp.to_dict()
    prof = _profile()
    all_pillars = prof["research_pillars"]["primary"] + prof["research_pillars"]["secondary"]
    text = " ".join(str(d.get(k, "")) for k in ("title", "purpose", "mechanism"))
    matched = _detect_focus(text, all_pillars)

    llm_version = _llm_aims(d, matched)
    if llm_version:
        return llm_version
    return _template_aims(d, matched)
