"""
Wiser API Connector (AU + US)
Fetches fieldwork progress for Wiser-managed markets.
NOTE: API docs/credentials pending from Wiser. Stub returns mock data until available.
"""

import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

WISER_MARKETS = ["AU", "US"]


def _get_secret(key: str, default: str = "") -> str:
    val = os.getenv(key, "")
    if val:
        return val
    try:
        import streamlit as st
        return str(st.secrets.get(key, default))
    except Exception:
        return default


def is_configured() -> bool:
    return bool(_get_secret("WISER_API_KEY") and _get_secret("WISER_API_BASE_URL"))


def get_headers() -> dict:
    api_key = _get_secret("WISER_API_KEY")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def get_progress(date_from: str = None, date_to: str = None) -> list[dict]:
    """
    Returns unified progress rows for Wiser markets (AU, US).
    Falls back to stub/manual data if API not configured.
    date_from / date_to accepted for interface consistency; used when API supports it.
    """
    api_key = _get_secret("WISER_API_KEY")
    base_url = _get_secret("WISER_API_BASE_URL")
    if not api_key or not base_url:
        return _stub_data()

    rows = []
    try:
        resp = requests.get(
            f"{base_url}/api/projects/versuni-wave3/progress",
            headers=get_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("results", []):
            market = item.get("market", "??")
            category = item.get("category", "??")
            target = item.get("total_assigned", 0)
            completed = item.get("completed", 0)
            pct = round(completed / target * 100, 1) if target > 0 else 0
            rows.append({
                "market": market,
                "category": category,
                "platform": "wiser",
                "target": target,
                "completed": completed,
                "pct": pct,
                "last_updated": datetime.utcnow().isoformat(),
                "status": _status(pct),
            })
    except Exception as e:
        rows = _stub_data()
        rows[0]["error"] = str(e)
    return rows


def load_manual_upload(csv_path: str) -> list[dict]:
    """
    Fallback: load progress from a manually uploaded CSV from Wiser.
    Expected columns: market, category, target, completed
    """
    import pandas as pd
    df = pd.read_csv(csv_path)
    rows = []
    for _, row in df.iterrows():
        target = int(row.get("target", 0))
        completed = int(row.get("completed", 0))
        pct = round(completed / target * 100, 1) if target > 0 else 0
        rows.append({
            "market": row.get("market", "??"),
            "category": row.get("category", "??"),
            "platform": "wiser_manual",
            "target": target,
            "completed": completed,
            "pct": pct,
            "last_updated": datetime.utcnow().isoformat(),
            "status": _status(pct),
        })
    return rows


def _status(pct: float) -> str:
    if pct >= 100: return "complete"
    if pct >= 60:  return "on_track"
    if pct >= 30:  return "at_risk"
    return "critical"


def _stub_data() -> list[dict]:
    return [
        {"market": m, "category": c, "platform": "wiser",
         "target": 0, "completed": 0, "pct": 0,
         "last_updated": datetime.utcnow().isoformat(),
         "status": "pending", "note": "Awaiting Wiser API credentials"}
        for m in ["AU", "US"]
        for c in ["FAEM", "Airfryer"]
    ]
