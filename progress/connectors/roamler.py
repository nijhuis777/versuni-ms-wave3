"""
Roamler API Connector
Fetches fieldwork progress and submission data.

Supports date-range filtering so 2025 Wave II data can be used
as a dashboard preview before Wave III fieldwork begins.

Date filter is controlled via .env:
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

BASE_URL    = os.getenv("ROAMLER_API_BASE_URL", "https://api.roamler.com")
API_KEY     = os.getenv("ROAMLER_API_KEY", "")
CUSTOMER_ID = os.getenv("ROAMLER_CUSTOMER_ID", "")

# Date range filter — default to Wave III window, override to 2025 for preview
DATE_FROM = os.getenv("ROAMLER_DATE_FROM", "2026-03-09")
DATE_TO   = os.getenv("ROAMLER_DATE_TO",   "2026-06-30")

ROAMLER_MARKETS = ["DE", "FR", "NL", "UK", "TR"]


def get_headers() -> dict:
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "X-Customer-Id": CUSTOMER_ID,
    }


def is_configured() -> bool:
    return bool(API_KEY and BASE_URL and CUSTOMER_ID)


def fetch_all_jobs(date_from: str = DATE_FROM, date_to: str = DATE_TO) -> list[dict]:
    """Fetch all Roamler jobs within the date window."""
    resp = requests.get(
        f"{BASE_URL}/v1/jobs",
        headers=get_headers(),
        params={
            "customer_id": CUSTOMER_ID,
            "start_date_from": date_from,
            "start_date_to": date_to,
            "limit": 200,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("jobs", [])


def fetch_submissions(job_id: str, date_from: str = DATE_FROM, date_to: str = DATE_TO) -> list[dict]:
    """Fetch all completed submissions for a single job."""
    results = []
    page = 1
    while True:
        resp = requests.get(
            f"{BASE_URL}/v1/jobs/{job_id}/submissions",
            headers=get_headers(),
            params={
                "status": "approved",
                "submitted_from": date_from,
                "submitted_to": date_to,
                "page": page,
                "per_page": 100,
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("submissions", [])
        results.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return results


def pull_all_submissions(date_from: str = DATE_FROM, date_to: str = DATE_TO) -> list[dict]:
    """
    Pull all approved submissions across all jobs in the date window.
    Used by the ETL pipeline to build the master dataset.
    Returns flat list of submission dicts.
    """
    if not is_configured():
        return []

    all_submissions = []
    jobs = fetch_all_jobs(date_from, date_to)
    print(f"  Found {len(jobs)} Roamler jobs ({date_from} → {date_to})")

    for job in jobs:
        job_id = job.get("id")
        market = job.get("market_code", "??")
        category = job.get("category_code", "??")
        subs = fetch_submissions(job_id, date_from, date_to)
        for s in subs:
            s["_market"] = market
            s["_category"] = category
            s["_job_id"] = job_id
        all_submissions.extend(subs)
        print(f"    {market} / {category}: {len(subs)} submissions")

    return all_submissions


def get_progress(date_from: str = DATE_FROM, date_to: str = DATE_TO) -> list[dict]:
    """
    Returns unified progress rows for all Roamler markets.
    Each row: {market, category, platform, target, completed, pct, last_updated}
    """
    if not is_configured():
        return _stub_data()

    rows = []
    try:
        jobs = fetch_all_jobs(date_from, date_to)
        for job in jobs:
            market = job.get("market_code", "??")
            category = job.get("category_code", "??")
            target = job.get("target_completions", 0)
            completed = job.get("completed_count", 0)
            pct = round(completed / target * 100, 1) if target > 0 else 0
            rows.append({
                "market": market,
                "category": category,
                "platform": "roamler",
                "target": target,
                "completed": completed,
                "pct": pct,
                "last_updated": datetime.utcnow().isoformat(),
                "status": _status(pct),
                "date_from": date_from,
                "date_to": date_to,
            })
    except Exception as e:
        rows = _stub_data()
        rows[0]["error"] = str(e)
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
