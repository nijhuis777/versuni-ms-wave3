"""
Roamler API Connector
Fetches fieldwork progress for all Roamler markets.
"""

import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("ROAMLER_API_BASE_URL", "https://api.roamler.com")
API_KEY  = os.getenv("ROAMLER_API_KEY", "")
CUSTOMER_ID = os.getenv("ROAMLER_CUSTOMER_ID", "")

ROAMLER_MARKETS = ["DE", "FR", "NL", "UK", "TR"]


def get_headers() -> dict:
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "X-Customer-Id": CUSTOMER_ID,
    }


def fetch_job_progress(job_id: str) -> dict:
    """Fetch completion stats for a single Roamler job (= one category in one market)."""
    resp = requests.get(
        f"{BASE_URL}/v1/jobs/{job_id}/progress",
        headers=get_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_all_jobs(wave_tag: str = "wave3_2026") -> list[dict]:
    """Fetch all jobs tagged for Wave III."""
    resp = requests.get(
        f"{BASE_URL}/v1/jobs",
        headers=get_headers(),
        params={"tag": wave_tag, "limit": 200},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("jobs", [])


def get_progress() -> list[dict]:
    """
    Returns unified progress rows for all Roamler markets.
    Each row: {market, category, platform, target, completed, pct, last_updated}
    """
    rows = []
    try:
        jobs = fetch_all_jobs()
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
            })
    except Exception as e:
        # Return stub data if API not yet available
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
        for c in ["FAEM", "SAEM", "Airfryer"]
    ]
