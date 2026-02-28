"""
Standalone diagnostic for the Roamler connector.

Run from the repo root:
    python test_roamler.py

Reads credentials from .env (same as the dashboard).
Does NOT require Streamlit to be running.
"""

import sys
from pathlib import Path

# Make sure the repo root is on sys.path so imports work
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from progress.connectors.roamler import (
    is_configured, fetch_all_jobs, fetch_submissions,
    _parse_market, _parse_category, _norm, _resolve_market,
    ROAMLER_MARKETS, _MARKET_ALIASES,
)

SEPARATOR = "─" * 72


def section(title: str):
    print(f"\n{SEPARATOR}")
    print(f"  {title}")
    print(SEPARATOR)


# ── 1. Config check ────────────────────────────────────────────────────────
section("1 · API configuration")
if is_configured():
    print("  ✅  ROAMLER_API_KEY is set")
else:
    print("  ❌  ROAMLER_API_KEY not found in .env or environment")
    print("      → check that .env exists and contains ROAMLER_API_KEY=...")
    sys.exit(1)

# ── 2. Norm / parsing unit tests ───────────────────────────────────────────
section("2 · _norm() and _resolve_market() unit tests")

norm_cases = [
    ("2025 - January - Versuni - FAEM - DE",      "2025 - January - Versuni - FAEM - DE"),
    ("2025 - January - Versuni \u2013 FAEM \u2013 DE",  "2025 - January - Versuni - FAEM - DE"),
    ("2025 - January - Versuni \u2014 FAEM \u2014 DE",  "2025 - January - Versuni - FAEM - DE"),
]
for raw, expected in norm_cases:
    result = _norm(raw)
    ok = "✅" if result == expected else "❌"
    print(f"  {ok}  _norm({raw!r})")
    if result != expected:
        print(f"      expected: {expected!r}")
        print(f"      got:      {result!r}")

resolve_cases = [
    ("DE",  "DE"),
    ("FR",  "FR"),
    ("PL",  "POL"),
    ("NL",  "NL"),
    ("UK",  "UK"),
    ("XX",  None),
]
for code, expected in resolve_cases:
    result = _resolve_market(code)
    ok = "✅" if result == expected else "❌"
    print(f"  {ok}  _resolve_market({code!r}) → {result!r}")

# ── 3. Fetch all jobs ──────────────────────────────────────────────────────
section("3 · fetch_all_jobs()")
try:
    jobs = fetch_all_jobs()
except Exception as e:
    print(f"  ❌  Exception: {e}")
    sys.exit(1)

print(f"  ✅  Fetched {len(jobs)} jobs total")

# ── 4. Parse market / category for all jobs ────────────────────────────────
section("4 · Market & category parsing for all jobs")

markets_found: dict[str, int] = {}
unknown_market: list[dict] = []

for j in jobs:
    m = _parse_market(j)
    c = _parse_category(j)
    markets_found[m] = markets_found.get(m, 0) + 1
    if m == "??":
        unknown_market.append({
            "workingTitle": j.get("workingTitle", ""),
            "title":        j.get("title", ""),
        })

print(f"  Markets found: {dict(sorted(markets_found.items()))}")
print(f"  Jobs with unknown market (??): {len(unknown_market)}")
for u in unknown_market[:10]:   # show first 10
    print(f"    workingTitle={u['workingTitle']!r}  title={u['title']!r}")

# ── 5. Fetch submissions for first 3 known jobs ────────────────────────────
section("5 · fetch_submissions() sample (first 3 known jobs, 2025 date range)")

DATE_FROM = "2025-01-01"
DATE_TO   = "2025-12-31"

known_jobs = [j for j in jobs if _parse_market(j) != "??"][:3]
if not known_jobs:
    print("  ⚠️  No jobs with a recognised market — cannot test submissions")
else:
    for j in known_jobs:
        jid = str(j.get("id") or j.get("Id") or "")
        m   = _parse_market(j)
        c   = _parse_category(j)
        wt  = j.get("workingTitle", "")
        try:
            subs = fetch_submissions(jid, DATE_FROM, DATE_TO)
            print(f"  ✅  job {jid} ({m}/{c}) → {len(subs)} submissions  |  {wt!r}")
        except Exception as e:
            print(f"  ❌  job {jid} ({m}/{c}) → EXCEPTION: {e}  |  {wt!r}")

# ── 6. Full get_progress() call ────────────────────────────────────────────
section("6 · get_progress() for 2025 range (full run — may take a minute)")
from progress.connectors.roamler import get_progress

try:
    rows = get_progress(DATE_FROM, DATE_TO)
except Exception as e:
    print(f"  ❌  Exception: {e}")
    sys.exit(1)

total_completed = sum(r.get("completed", 0) for r in rows)
print(f"  Returned {len(rows)} rows, {total_completed} total completions")

errors = [r for r in rows if "error" in r]
notes  = [r for r in rows if "note"  in r]
if errors:
    print(f"  ⚠️  Error row: {errors[0]['error']}")
if notes:
    print(f"  ℹ️  Note row: {notes[0]['note']}")

print()
for r in rows:
    skip = r.get("skipped_jobs", 0)
    skip_ids = r.get("skipped_job_ids", "")
    line = f"  {r['market']:4s} / {r['category']:25s} completed={r['completed']:4d}"
    if skip:
        line += f"  (skipped={skip})"
    print(line)

if skip_ids:
    print(f"\n  Skipped job IDs: {skip_ids[:400]}")

print(f"\n{SEPARATOR}")
print("  Done — check the output above for ❌ markers.")
print(SEPARATOR)
