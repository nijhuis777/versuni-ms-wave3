"""
Roamler API Connector
Fetches fieldwork progress and submission data.

Supports date-range filtering so 2025 Wave II data can be used
as a dashboard preview before Wave III fieldwork begins.

Date filter is controlled via .env or Streamlit secrets:
  ROAMLER_DATE_FROM=2025-01-01   (use 2025 data for preview)
  ROAMLER_DATE_TO=2025-12-31
  -- or for live Wave III --
  ROAMLER_DATE_FROM=2026-03-09
  ROAMLER_DATE_TO=2026-06-30
"""

import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

ROAMLER_MARKETS = ["DE", "FR", "NL", "UK", "TR", "AU", "BR", "US", "POL"]

# Some job titles use em/en dashes instead of plain hyphens — normalise first.
_DASH_NORM = str.maketrans({'\u2013': '-', '\u2014': '-', '\u2012': '-'})

def _norm(s: str) -> str:
    """Replace en/em dashes with plain hyphens for consistent ' - ' splitting."""
    return s.translate(_DASH_NORM)

# Roamler uses 'PL' for Poland; our canonical code is 'POL'.
_MARKET_ALIASES: dict[str, str] = {"PL": "POL"}

# Map keywords found in workingTitle → canonical category name.
# ORDER MATTERS: more specific strings must come before shorter/overlapping ones.
CATEGORY_KEYWORDS = {
    # ── Coffee machines ───────────────────────────────────────────────────────
    "full auto":           "FAEM",
    "fully auto":          "FAEM",
    "faem":                "FAEM",
    "floorcare":           "FAEM",   # legacy spelling

    "semi":                "SAEM",
    "baristina":           "SAEM",
    "saem":                "SAEM",

    "portioned":           "Portioned_Espresso",
    "pe ":                 "Portioned_Espresso",   # "PE " with space to avoid false positives

    # ── Kitchen appliances ────────────────────────────────────────────────────
    "airfryer":            "Airfryer",
    "air fryer":           "Airfryer",

    "blender":             "Blender",

    "juicer":              "Juicer_Mixer",
    "mixer":               "Juicer_Mixer",
    "grinder":             "Juicer_Mixer",

    "cooker":              "Cooker_Griller",
    "griller":             "Cooker_Griller",

    # ── Floor care ────────────────────────────────────────────────────────────
    "w&d":                 "Handstick_WD",    # "W&D" = Wet & Dry — must come before plain handstick
    "wet & dry":           "Handstick_WD",
    "wet dry":             "Handstick_WD",
    "wet":                 "Handstick_WD",    # "wet" alone also means W&D

    "handstick":           "Handstick_Dry",   # remaining handstick jobs = Dry variant
    "hand stick":          "Handstick_Dry",

    "rvc":                 "RVC",
    "robot":               "RVC",

    # ── Garment / fabric care ─────────────────────────────────────────────────
    "all-in-one":          "All_in_One",
    "all in one":          "All_in_One",

    "steam iron":          "Steam_Iron",      # must come before plain "steam"
    "steam generator":     "Steam_Generator", # must come before "steam gen"
    "steam gen":           "Steam_Generator",
    "stand steamer":       "Stand_Steamer",   # must come before plain "steamer"
    "stand steam":         "Stand_Steamer",
    "handheld":            "Handheld_Steamer",
    "steamer":             "Handheld_Steamer",

    "dry iron":            "Dry_Iron",
}


# ─── Config helpers (lazy — read at call time, not import time) ───────────────

def _get_secret(key: str, default: str = "") -> str:
    """Read a secret from env var, then Streamlit secrets as fallback.

    Module-level os.getenv() fails on Streamlit Cloud when env vars are
    injected after the module is imported. This function reads fresh each call.
    """
    val = os.getenv(key, "")
    if val:
        return val
    try:
        import streamlit as st
        return str(st.secrets.get(key, default))
    except Exception:
        return default


def _base_url() -> str:
    return _get_secret("ROAMLER_API_BASE_URL", "https://api-customer.roamler.com")


def _api_key() -> str:
    return _get_secret("ROAMLER_API_KEY", "")


def get_headers() -> dict:
    return {"X-Roamler-Api-Key": _api_key()}


def is_configured() -> bool:
    return bool(_api_key())


# ─── Parsing helpers ──────────────────────────────────────────────────────────

def _resolve_market(code: str) -> str | None:
    """Return canonical market code or None if unknown."""
    code = _MARKET_ALIASES.get(code, code)
    return code if code in ROAMLER_MARKETS else None


def _parse_market(job: dict) -> str:
    """Extract market code from workingTitle or title.

    Normalises em/en dashes to plain hyphens before splitting so titles like
    '2025 - January - Versuni – Handheld Steamer – FR' parse correctly.
    Resolves 'PL' → 'POL' via _MARKET_ALIASES.
    """
    wt = _norm(job.get("workingTitle") or "")
    parts = [p.strip() for p in wt.split(" - ")]

    # 1. Last segment (canonical position)
    if parts:
        m = _resolve_market(parts[-1].upper())
        if m:
            return m

    # 2. Any segment — handles non-standard orderings
    for p in parts:
        m = _resolve_market(p.upper())
        if m:
            return m

    # 3. Scan title field
    all_codes = set(ROAMLER_MARKETS) | set(_MARKET_ALIASES)
    title = _norm(job.get("title") or "").upper()
    for code in all_codes:
        if title == code or title.endswith(f" {code}") or f" {code} " in f" {title} ":
            return _MARKET_ALIASES.get(code, code)

    return "??"


# Words to skip when scanning segments for a category keyword.
_SKIP_WORDS = {
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "versuni", "roamler", "philips",
}


def _parse_category(job: dict) -> str:
    """Extract category from workingTitle.

    Tries the second-to-last segment first (expected format), then scans
    every segment (skipping years, months, market codes, brand names),
    then falls back to the title field.  Returns the raw segment text if
    no keyword matches so unrecognised categories surface in the dashboard
    rather than being silently dropped.
    """
    wt = _norm(job.get("workingTitle") or "")
    parts = [p.strip() for p in wt.split(" - ")]

    # 1. Second-to-last segment (canonical position)
    if len(parts) >= 2:
        cat_raw = parts[-2].lower()
        for kw, cat in CATEGORY_KEYWORDS.items():
            if kw in cat_raw:
                return cat

    # 2. All segments — handles non-standard orderings
    all_market_codes = set(ROAMLER_MARKETS) | set(_MARKET_ALIASES)
    for p in parts:
        p_lower = p.lower()
        if (p.upper() in all_market_codes  # skip market codes
                or p.isdigit()             # skip year numbers
                or p_lower in _SKIP_WORDS):# skip months / brand names
            continue
        for kw, cat in CATEGORY_KEYWORDS.items():
            if kw in p_lower:
                return cat

    # 3. Fallback: scan title field
    title = _norm(job.get("title") or "").lower()
    for kw, cat in CATEGORY_KEYWORDS.items():
        if kw in title:
            return cat

    # 4. Return raw second-to-last segment so unrecognised names are visible
    if len(parts) >= 2:
        return parts[-2].strip() or "??"

    return "??"


def _job_id(job: dict) -> str:
    return str(job.get("id") or job.get("Id") or job.get("jobId") or "")


# ─── API calls ────────────────────────────────────────────────────────────────

_JOBS_PAGE_SIZE = 200   # explicit large page size to avoid missing jobs


def fetch_all_jobs() -> list[dict]:
    """Fetch all Roamler jobs, paginating until the API is exhausted.

    Never uses batch size to decide when to stop — the API page size is
    unknown and may differ from any value we request.  Instead we stop when:
      1. The API returns an empty batch (clean end-of-data), OR
      2. Every job in the batch was already seen (API ignores the page param
         and keeps returning the same first page).

    A hard cap of 50 pages guards against infinite loops.
    """
    results = []
    seen_ids: set[str] = set()
    page = 1          # Roamler API is 1-indexed (page=0 == page=1, causing duplicates)
    base = _base_url()
    MAX_PAGES = 50

    while page <= MAX_PAGES:
        resp = requests.get(
            f"{base}/v1/Jobs",
            headers=get_headers(),
            params={"page": page, "take": _JOBS_PAGE_SIZE},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        batch = data if isinstance(data, list) else data.get("jobs", data.get("Jobs", []))

        if not batch:
            break  # empty page → no more jobs

        new_jobs = [j for j in batch if _job_id(j) not in seen_ids]
        if not new_jobs:
            break  # all jobs in this batch already seen → no real next page

        for j in new_jobs:
            seen_ids.add(_job_id(j))
        results.extend(new_jobs)
        page += 1  # always advance — never stop based on batch size

    return results


def fetch_submissions(job_id: str, date_from: str = None, date_to: str = None) -> list[dict]:
    """Fetch all submissions for a single job within the date window."""
    if date_from is None:
        date_from = _get_secret("ROAMLER_DATE_FROM", "2026-03-09")
    if date_to is None:
        date_to = _get_secret("ROAMLER_DATE_TO", "2026-06-30")

    results = []
    page = 1
    base = _base_url()
    while True:
        resp = requests.get(
            f"{base}/v1/Jobs/{job_id}/Submissions",
            headers=get_headers(),
            params={
                "fromDate": f"{date_from}T00:00:00",
                "toDate": f"{date_to}T23:59:59",
                "page": page,
                "take": 1000,
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        batch = data if isinstance(data, list) else data.get("submissions", data.get("Submissions", []))
        results.extend(batch)
        if len(batch) < 1000:
            break
        page += 1
    return results


def pull_all_submissions(date_from: str = None, date_to: str = None) -> list[dict]:
    """
    Pull all approved submissions across all jobs in the date window.
    Used by the ETL pipeline to build the master dataset.
    Returns flat list of submission dicts.
    """
    if date_from is None:
        date_from = _get_secret("ROAMLER_DATE_FROM", "2026-03-09")
    if date_to is None:
        date_to = _get_secret("ROAMLER_DATE_TO", "2026-06-30")

    if not is_configured():
        return []

    all_submissions = []
    jobs = fetch_all_jobs()
    print(f"  Found {len(jobs)} Roamler jobs ({date_from} → {date_to})")

    for job in jobs:
        job_id = _job_id(job)
        market = _parse_market(job)
        category = _parse_category(job)
        try:
            subs = fetch_submissions(job_id, date_from, date_to)
        except Exception as job_err:
            print(f"    SKIP job {job_id} ({market}/{category}): {job_err}")
            continue
        for s in subs:
            s["_market"] = market
            s["_category"] = category
            s["_job_id"] = job_id
        all_submissions.extend(subs)
        print(f"    {market} / {category}: {len(subs)} submissions")

    return all_submissions


def debug_jobs() -> tuple[list[dict], dict]:
    """Return all jobs with parsed fields, plus fetch metadata.
    Used by the dashboard debug expander to diagnose missing submissions.
    Returns (rows, meta) where meta has total_fetched, pages_used.
    """
    if not is_configured():
        return [], {"error": "API not configured"}
    try:
        jobs = fetch_all_jobs()
    except Exception as e:
        return [], {"error": str(e)}
    rows = [
        {
            "id":            _job_id(j),
            "market":        _parse_market(j),
            "category":      _parse_category(j),
            "workingTitle":  j.get("workingTitle", ""),
            "title":         j.get("title", ""),
        }
        for j in jobs
    ]
    skipped = [r for r in rows if r["market"] == "??"]
    meta = {
        "total_fetched": len(jobs),
        "skipped_unknown_market": len(skipped),
        "markets_found": sorted({r["market"] for r in rows if r["market"] != "??"}),
    }
    return rows, meta


def get_progress(date_from: str = None, date_to: str = None) -> list[dict]:
    """
    Returns unified progress rows for all Roamler markets.
    Each row: {market, category, platform, target, completed, pct, last_updated}
    """
    if date_from is None:
        date_from = _get_secret("ROAMLER_DATE_FROM", "2026-03-09")
    if date_to is None:
        date_to = _get_secret("ROAMLER_DATE_TO", "2026-06-30")

    if not is_configured():
        return _stub_data()

    counts: dict[tuple, int] = {}
    skipped: list[str] = []
    try:
        jobs = fetch_all_jobs()
    except Exception as e:
        rows = _stub_data()
        rows[0]["error"] = str(e)
        return rows

    # Fetch submissions per job — each job is independent; a failing job is
    # logged and skipped rather than aborting the entire data pull.
    for job in jobs:
        market = _parse_market(job)
        category = _parse_category(job)
        if market == "??":
            continue  # Can't assign to a market — skip
        jid = _job_id(job)
        try:
            subs = fetch_submissions(jid, date_from, date_to)
        except Exception as job_err:
            skipped.append(f"{jid} ({market}/{category}): {job_err}")
            continue
        key = (market, category)
        counts[key] = counts.get(key, 0) + len(subs)

    rows = []
    for (market, category), completed in counts.items():
        rows.append({
            "market": market,
            "category": category,
            "platform": "roamler",
            "target": 0,       # No target in API — merged from targets.yaml in tracker
            "completed": completed,
            "pct": 0,          # Recomputed after targets are merged in tracker
            "last_updated": datetime.utcnow().isoformat(),
            "status": "complete" if completed > 0 else "pending",
            "date_from": date_from,
            "date_to": date_to,
            "skipped_jobs": len(skipped),
        })

    if not rows:
        rows = _stub_data()
    if skipped:
        rows[0]["skipped_job_ids"] = "; ".join(skipped)
    return rows


def _status(pct: float) -> str:
    if pct >= 100: return "complete"
    if pct >= 60:  return "on_track"
    if pct >= 30:  return "at_risk"
    return "critical"


def _stub_data() -> list[dict]:
    """Placeholder data used when API credentials are not yet set up."""
    return [
        {"market": m, "category": c, "platform": "roamler",
         "target": 0, "completed": 0, "pct": 0,
         "last_updated": datetime.utcnow().isoformat(),
         "status": "pending", "note": "API not yet configured"}
        for m in ["DE", "FR", "NL", "UK", "TR"]
        for c in ["FAEM", "Airfryer"]
    ]
