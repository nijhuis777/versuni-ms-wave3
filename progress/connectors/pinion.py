"""
Pinion API Connector (BR)
Fetches fieldwork progress for Pinion-managed markets.
NOTE: API docs/credentials pending from Pinion. Stub returns mock data until available.
"""

import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("PINION_API_BASE_URL", "")
API_KEY  = os.getenv("PINION_API_KEY", "")


def get_headers() -> dict:
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }


def get_progress() -> list[dict]:
    """
    Returns unified progress rows for Pinion markets (BR).
    Falls back to stub data if API not yet configured.
    """
    if not API_KEY or not BASE_URL:
        return _stub_data()

    rows = []
    try:
        resp = requests.get(
            f"{BASE_URL}/api/v1/projects/versuni/progress",
            headers=get_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("data", []):
            target = int(item.get("quota", 0))
            completed = int(item.get("completes", 0))
            pct = round(completed / target * 100, 1) if target > 0 else 0
            rows.append({
                "market": "BR",
                "category": item.get("category_code", "??"),
                "platform": "pinion",
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
    """Fallback: load from manually provided Pinion export."""
    import pandas as pd
    df = pd.read_csv(csv_path)
    rows = []
    for _, row in df.iterrows():
        target = int(row.get("target", 0))
        completed = int(row.get("completed", 0))
        pct = round(completed / target * 100, 1) if target > 0 else 0
        rows.append({
            "market": "BR",
            "category": row.get("category", "??"),
            "platform": "pinion_manual",
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
        {"market": "BR", "category": c, "platform": "pinion",
         "target": 0, "completed": 0, "pct": 0,
         "last_updated": datetime.utcnow().isoformat(),
         "status": "pending", "note": "Awaiting Pinion API credentials"}
        for c in ["Airfryer", "Blender", "FAEM"]
    ]
