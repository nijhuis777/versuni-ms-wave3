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

def _parse_market(job: dict) -> str:
    """Extract 2-letter market code.
    workingTitle format: '2025 - January - Versuni - Airfryer - FR'
    Market code is always the last ' - ' segment.
    """
    wt = job.get("workingTitle") or ""
    parts = [p.strip() for p in wt.split(" - ")]
    if parts:
        candidate = parts[-1].upper()
        if candidate in ROAMLER_MARKETS:
            return candidate
    # Fallback: scan title for market codes
    title = (job.get("title") or "").upper()
    for m in ROAMLER_MARKETS:
        if title.endswith(f" {m}") or f" {m} " in f" {title} ":
            return m
    return "??"


def _parse_category(job: dict) -> str:
    """Extract category from workingTitle second-to-last segment.
    workingTitle format: '2025 - January - Versuni - Airfryer - FR'
    Category is always the second-to-last ' - ' segment.
    """
    wt = job.get("workingTitle") or ""
    parts = [p.strip() for p in wt.split(" - ")]
    if len(parts) >= 2:
        cat_raw = parts[-2].lower()
        for kw, cat in CATEGORY_KEYWORDS.items():
            if kw in cat_raw:
                return cat
        # No keyword match — return the raw segment so unrecognised categories
        # are visible in the dashboard rather than silently dropped.
        return parts[-2].strip() or "??"
    # Fallback: scan title
    title = (job.get("title") or "").lower()
    for kw, cat in CATEGORY_KEYWORDS.items():
        if kw in title:
            return cat
    return "??"


def _job_id(job: dict) -> str:
    return str(job.get("id") or job.get("Id") or job.get("jobId") or "")


# ─── API calls ────────────────────────────────────────────────────────────────

def fetch_all_jobs() -> list[dict]:
    """Fetch all Roamler jobs (paginated)."""
    results = []
    page = 0
    base = _base_url()
    while True:
        resp = requests.get(
            f"{base}/v1/Jobs",
            headers=get_headers(),
            params={"page": page},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        batch = data if isinstance(data, list) else data.get("jobs", data.get("Jobs", []))
        results.extend(batch)
        if len(batch) < 50:
            break
        page += 1
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
