# Grant Radar

Weekly scan of NIH, foundations, DoD, NSF, and ARPA-H funding opportunities,
filtered against JP McGinnis's research profile. Delivers:

- a **static dashboard** (filterable table, deadline calendar, drafts),
- a **Monday morning plain-text email** with new opportunities, the top 3
  with draft aims skeletons attached, and a 120-day deadline runway table,
- **persistent per-opportunity status** (new / interested / drafting /
  submitted / declined / dismissed) in your browser's localStorage.

The whole thing is a GitHub repo. GitHub Actions runs the pipeline each
Monday at 06:00 CT, commits the updated data, deploys the dashboard to
GitHub Pages, and sends the email from your Gmail to yourself via SMTP.

---

## Why this exists

The failure mode this kills: *"I would have applied for that if I'd
known the LOI was due two weeks ago."* With about forty active
foundation + agency feeds and dozens of NIH FOAs posted each week, the
only way to catch everything is to automate the triage.

## Setup

### 1. Create a new GitHub repo and push this folder

```bash
cd grant-radar
git init
git add .
git commit -m "initial commit"
gh repo create jpmcginnis1/grant-radar --private --source=. --push
```

### 2. Turn on GitHub Pages

Repo → **Settings → Pages** → set **Source** to **GitHub Actions**.

### 3. Create a Gmail app password

The radar sends from your Gmail to your Gmail via SMTP, which needs
an app password (not your regular Gmail password).

1. Make sure 2-Step Verification is on for the account at
   <https://myaccount.google.com/security>.
2. Go to <https://myaccount.google.com/apppasswords>.
3. Pick "Mail" / "Other (Custom name)", name it "Grant Radar", and
   generate.
4. Copy the 16-character password Google shows you (there are no
   spaces in the actual value — the display just groups them).

### 4. Add the secrets

Repo → **Settings → Secrets and variables → Actions**.

| Secret | Value |
| --- | --- |
| `SMTP_USER` | `jpmcginnis1@gmail.com` |
| `SMTP_PASS` | the 16-character Gmail app password from step 3 |
| `DIGEST_TO` | `jpmcginnis1@gmail.com` (where to send the digest; defaults to `SMTP_USER` if omitted) |

### 5. Set the site URL variable

Settings → Variables (not secrets) → add `SITE_URL` =
`https://jpmcginnis1.github.io/grant-radar/`. The email footer and
"open dashboard" link use this.

### 6. Trigger the first run

Repo → **Actions → Weekly grant radar → Run workflow**.
The run commits the first `opportunities.json`, deploys the dashboard,
and sends a seed email. Afterward it fires automatically every Monday
at 06:00 CT.

## Running locally

```bash
pip install -r requirements.txt

# Full run (hits all sources, ~2 min)
python pipeline.py

# Smoke test one source
python pipeline.py --only damon_runyon --dry-run

# Build the email text without sending (writes site/data/digest.txt)
python send_digest.py

# Send a real test email from the terminal
SMTP_USER=jpmcginnis1@gmail.com \
SMTP_PASS='your app password here' \
python send_digest.py

# Preview the dashboard
python -m http.server --directory site 8000
# → http://localhost:8000
```

## How it works

```
sources.yaml  ─┐
profile.yaml  ─┼─► pipeline.py ─► data/opportunities.json
scrapers/*    ─┘       │              │
                       ├─► site/data/opportunities.json  (dashboard reads this)
                       ├─► site/data/digest.json         (email reads this)
                       └─► drafts/<id>.md                (per-opportunity aims)
```

**Fit score (0–100).** Each opportunity gets:

| Component | Max | What it rewards |
| --- | --- | --- |
| Pillar coverage | 50 | How many of JP's research pillars (AAV, enhancer, ex vivo, cerebrovascular, scATAC, etc.) show up in the title / purpose |
| Mechanism fit   | 20 | Right career stage (K's and physician-scientist foundations score highest) |
| Deadline runway | 15 | 45–180 day lead time ideal; <14 days is too tight; past-due = 0 |
| Budget fit      | 10 | Within the `budget_floor_usd` / `budget_ceiling_usd` set in `profile.yaml` |
| Eligibility     | 5  | Physician-scientist, early-career, new-investigator cues |

**Aims-skeleton generator.** Attached to the top 3 *new* opportunities
per run. Deterministic template that pulls in the mechanism/sponsor
language and inserts `<PRELIM>` / `<SAMPLE>` tags where JP needs to
plug in actual lab data. Set `GRANT_RADAR_LLM_PROVIDER` in the
workflow env to upgrade this to LLM-generated prose later.

**Email format.** Plain text. Renders cleanly on every mail client
including iOS Mail on a dim screen at 06:30 CT, never gets stripped
by a security gateway, and links are still clickable. If you ever
want HTML, swap the body-builder in `send_digest.py` and set the
message content type accordingly.

## Tuning

**Add a source.** Edit `sources.yaml`. For a foundation page the
`html_generic` scraper usually works out of the box. For
higher-fidelity extraction, drop a per-source parser in
`scrapers/foundations/<name>.py` and dispatch to it from
`scrapers/__init__.py`.

**Change what the scorer rewards.** Edit `profile.yaml` — add or
reweight research pillars, change the budget floor/ceiling, or add
exclusion terms. The scorer re-reads the file on every run.

**Adjust frequency.** Change the cron line in
`.github/workflows/weekly.yml`. Twice weekly:
`0 11 * * 1,4` (Mon + Thu). Daily during a push: `0 11 * * *`.

**Change the top-N aims generation.** `attach_aims_to_top(..., top_n=3)`
in `pipeline.py`.

## Files

```
grant-radar/
├── sources.yaml           # feed registry
├── profile.yaml           # JP's pillars + preferences
├── schema.py              # Opportunity dataclass
├── pipeline.py            # orchestrator
├── send_digest.py         # weekly email (Gmail SMTP, plain text)
├── scrapers/
│   ├── nih_guide.py       # NIH Guide (JSON API + RSS fallback)
│   ├── nih_reporter.py    # NIH RePORTER funded-project signals
│   ├── html_generic.py    # generic foundation page scraper
│   └── nsf_funding.py     # NSF funding opportunities
├── scorer/
│   ├── fit.py             # 100-point rubric
│   └── aims_skeleton.py   # draft Specific Aims template
├── site/                  # dashboard (deployed to GitHub Pages)
│   ├── index.html
│   ├── assets/style.css   # Tufte-inspired
│   ├── assets/app.js
│   └── data/              # opportunities.json, digest.json
├── data/                  # canonical opportunities.json (merged across runs)
├── drafts/                # per-opportunity aims skeletons (<id>.md)
└── .github/workflows/weekly.yml
```

## Known limitations

- **Foundation page shapes drift.** The `html_generic` scraper
  extracts headings + deadlines by regex; when a foundation ships a
  redesign, the scraper will miss nuances. The source URL is always
  preserved so clicking through still works. Replace with a per-source
  parser when a feed matters enough to harden.
- **Date parsing is best-effort.** "Spring 2027" and "rolling" produce
  no due date; the dashboard treats those as rolling / unknown runway.
- **No LOI reminders yet.** Easy next step: a second cron that fires
  daily and emails only on T-14, T-7, T-1 for anything in `status =
  interested` or `drafting`.
