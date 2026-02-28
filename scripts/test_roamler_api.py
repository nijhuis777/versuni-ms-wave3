"""
Quick test script — verify Roamler API connection and explore available data.
Run: py scripts/test_roamler_api.py

This will:
1. Verify the API key works (GET /v1/me)
2. List all available jobs
3. Show submission counts for the 2025 date range
4. Print one sample submission so we can map the field names
"""

import sys
import os
from pathlib import Path

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    print("Installing python-dotenv...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-dotenv"])
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")

import requests
import json

API_KEY  = os.getenv("ROAMLER_API_KEY", "")
BASE_URL = os.getenv("ROAMLER_API_BASE_URL", "https://api.roamler.com")
DATE_FROM = os.getenv("ROAMLER_DATE_FROM", "2025-01-01")
DATE_TO   = os.getenv("ROAMLER_DATE_TO",   "2025-12-31")

HEADERS = {"X-Roamler-Api-Key": API_KEY}


def check(label, resp):
    print(f"\n{'='*50}")
    print(f"  {label}")
    print(f"  Status: {resp.status_code}")
    if resp.ok:
        data = resp.json()
        print(f"  Response (first 2000 chars):")
        print(json.dumps(data, indent=2)[:2000])
        return data
    else:
        print(f"  ERROR: {resp.text[:500]}")
        return None


# ─── 1. Verify connection ────────────────────────────────────────────────────
print("\n>>> Step 1: Verify API key (GET /v1/me)")
r = requests.get(f"{BASE_URL}/v1/me", headers=HEADERS, timeout=15)
me = check("GET /v1/me", r)

# ─── 2. List jobs ─────────────────────────────────────────────────────────────
print("\n>>> Step 2: List all jobs (GET /v1/Jobs)")
r = requests.get(f"{BASE_URL}/v1/Jobs", headers=HEADERS, params={"page": 0}, timeout=30)
jobs = check("GET /v1/Jobs", r)

if jobs:
    job_list = jobs if isinstance(jobs, list) else jobs.get("jobs", [])
    print(f"\n  Total jobs found: {len(job_list)}")
    print("  Job titles:")
    for j in job_list[:20]:
        print(f"    [{j.get('id')}] {j.get('title', j.get('WorkingTitle', '?'))}")

    # ─── 3. Get submissions for first job ────────────────────────────────────
    if job_list:
        first_job = job_list[0]
        job_id = first_job.get("id")
        print(f"\n>>> Step 3: Get submissions for job {job_id} ({DATE_FROM} → {DATE_TO})")
        r = requests.get(
            f"{BASE_URL}/v1/Jobs/{job_id}/Submissions",
            headers=HEADERS,
            params={"fromDate": f"{DATE_FROM}T00:00:00", "toDate": f"{DATE_TO}T23:59:59",
                    "page": 1, "take": 5},
            timeout=30,
        )
        subs = check(f"GET /v1/Jobs/{job_id}/Submissions", r)

        # ─── 4. Get one full submission with answers ──────────────────────────
        if subs:
            sub_list = subs if isinstance(subs, list) else subs.get("submissions", [])
            if sub_list:
                first_sub = sub_list[0]
                sub_id = first_sub.get("id") or first_sub.get("submissionId") or first_sub.get("hRef", "").split("/")[-1]
                print(f"\n>>> Step 4: Full submission detail for {sub_id}")
                r = requests.get(
                    f"{BASE_URL}/v1/submissions/{sub_id}",
                    headers=HEADERS,
                    params={"includeAnswers": "true", "includeQuestions": "true"},
                    timeout=30,
                )
                check(f"GET /v1/submissions/{sub_id}", r)

print("\n✓ Done. Share this output to map the field names correctly.")
