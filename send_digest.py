"""
Weekly email digest sender.

Reads site/data/digest.json and sends a plain-text email via Gmail SMTP.
Plain text is deliberate: it renders cleanly on every mail client, is easy
to scan on a phone, and never gets stripped by a security gateway. Links
remain clickable.

Required environment variables:
    SMTP_USER   e.g. jpmcginnis1@gmail.com
    SMTP_PASS   a Google app password (NOT your regular Gmail password)
                → generate at https://myaccount.google.com/apppasswords
    DIGEST_TO   e.g. jpmcginnis1@gmail.com  (defaults to SMTP_USER)

Optional:
    SMTP_HOST   default smtp.gmail.com
    SMTP_PORT   default 587
    GRANT_RADAR_SITE_URL   footer link to the dashboard

Run locally:
    SMTP_USER=you@gmail.com SMTP_PASS='app password here' python send_digest.py
"""

import json
import os
import smtplib
import sys
from datetime import date
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIGEST_PATH = ROOT / "site" / "data" / "digest.json"
SITE_URL = os.environ.get(
    "GRANT_RADAR_SITE_URL",
    "https://jpmcginnis1.github.io/grant-radar/",
)


def _hr(char: str = "─", width: int = 65) -> str:
    return char * width


def _urgency_tag(days: int | None) -> str:
    if days is None:
        return ""
    if days < 0:
        return " · PAST DUE"
    if days <= 14:
        return f" · {days} DAYS OUT — tight"
    if days <= 30:
        return f" · {days} days out — soon"
    return f" · {days} days out"


def _top_opp_block(idx: int, o: dict) -> str:
    due = o.get("app_due") or o.get("loi_due")
    due_kind = "application" if o.get("app_due") == due else "LOI"
    today = date.today()
    days = None
    if due:
        try:
            days = (date.fromisoformat(due) - today).days
        except ValueError:
            pass
    lines = [
        f"{idx}. {o['title']}",
        f"   {o['sponsor']} · {o['mechanism']}",
    ]
    if due:
        lines.append(f"   DUE {due} ({due_kind}){_urgency_tag(days)}")
    lines.append(f"   Fit {o['fit_score']:.1f}/100 — {o.get('fit_rationale', '')}")
    if o.get("has_aims"):
        lines.append("   ★ Aims draft ready")
    lines.append(f"   → {o['source_url']}")
    return "\n".join(lines)


def _upcoming_row(u: dict) -> str:
    days_str = f"{u['days_out']:>3}d"
    kind = u["due_kind"]
    title = u["title"]
    # Truncate long titles so the table lines up on a phone
    if len(title) > 50:
        title = title[:47] + "..."
    return f"{days_str}  {u['due']} ({kind})  {title:<52s}  fit {u['fit_score']:.0f}"


def _other_opp_block(o: dict) -> str:
    due = o.get("app_due") or o.get("loi_due")
    due_kind = "App" if o.get("app_due") == due else "LOI"
    header = f"{o['title']} — fit {o['fit_score']:.1f}"
    sub = f"  {o['sponsor']} · {o.get('mechanism', '')}"
    if due:
        sub += f" · Due {due} ({due_kind})"
    url = f"  {o['source_url']}"
    return "\n".join([header, sub, url])


def build_text(digest: dict) -> str:
    today = digest["generated"]
    n_new = digest["new_count"]
    n_total = digest["total_tracked"]
    opp_word = "opportunity" if n_new == 1 else "opportunities"

    parts: list[str] = []

    parts.append(f"GRANT RADAR — {today}")
    parts.append("=" * 65)
    parts.append("")
    parts.append(f"{n_new} new {opp_word} this week · {n_total} tracked total")
    parts.append("")

    # Top 3
    if digest["top_three"]:
        parts.append("")
        parts.append("TOP 3 — AIMS SKELETONS ATTACHED")
        parts.append(_hr())
        parts.append("")
        for i, o in enumerate(digest["top_three"], start=1):
            parts.append(_top_opp_block(i, o))
            parts.append("")

    # Upcoming deadlines
    if digest["upcoming_deadlines"]:
        parts.append("")
        parts.append("UPCOMING DEADLINES (NEXT 120 DAYS)")
        parts.append(_hr())
        parts.append("")
        for u in digest["upcoming_deadlines"]:
            parts.append(_upcoming_row(u))
        parts.append("")

    # Also new (everything in new_this_week beyond the top 3)
    others = digest["new_this_week"][len(digest["top_three"]):]
    if others:
        parts.append("")
        parts.append("ALSO NEW THIS WEEK")
        parts.append(_hr())
        parts.append("")
        for o in others:
            parts.append(_other_opp_block(o))
            parts.append("")

    # Footer
    parts.append(_hr("─"))
    parts.append(f"Open the full dashboard: {SITE_URL}")
    parts.append("Edit profile.yaml to retune · edit sources.yaml to add feeds")
    parts.append("Replying to this email does nothing.")

    return "\n".join(parts)


def send_smtp(text: str, subject: str) -> None:
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASS"]
    to = os.environ.get("DIGEST_TO", user)
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.set_content(text)

    with smtplib.SMTP(host, port) as s:
        s.starttls()
        s.login(user, password)
        s.send_message(msg)


def main() -> int:
    if not DIGEST_PATH.exists():
        print(f"[digest] no digest file at {DIGEST_PATH}", file=sys.stderr)
        return 1
    digest = json.loads(DIGEST_PATH.read_text())
    if digest["new_count"] == 0 and not digest["upcoming_deadlines"]:
        print("[digest] nothing to send", file=sys.stderr)
        return 0

    text = build_text(digest)

    # Subject: date + new count + urgent count
    urgent = sum(1 for u in digest["upcoming_deadlines"] if u["days_out"] <= 30)
    subject = (
        f"Grant Radar — {digest['generated']} · "
        f"{digest['new_count']} new, {urgent} due in 30d"
    )

    if "SMTP_USER" in os.environ and "SMTP_PASS" in os.environ:
        send_smtp(text, subject)
        print(f"[digest] sent to {os.environ.get('DIGEST_TO', os.environ['SMTP_USER'])}",
              file=sys.stderr)
    else:
        # No SMTP credentials — write to disk for inspection
        out = ROOT / "site" / "data" / "digest.txt"
        out.write_text(text)
        print(f"[digest] no SMTP creds; wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
