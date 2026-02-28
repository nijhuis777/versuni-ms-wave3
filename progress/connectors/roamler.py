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
from concurrent.futures import ThreadPoolExecutor
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

_JOBS_PAGE_SIZE = 50   # only used by raw_jobs_page() diagnostic; NOT sent in production calls


def raw_jobs_page(page: int = 1) -> dict:
    """Fetch /v1/Jobs with multiple parameter combinations to diagnose issues.
    Tries: no params, page-only, page+take=50, page+take=200.
    """
    base = _base_url()
    url  = f"{base}/v1/Jobs"
    key  = _api_key()
    hdrs = get_headers()

    key_info = {
        "key_length":     len(key),
        "key_preview":    f"{key[:4]}…{key[-4:]}" if len(key) >= 8 else "(too short)",
        "key_has_spaces": key != key.strip(),
        "base_url":       base,
    }

    # Try multiple parameter combos to isolate the issue
    combos = [
        ("no_params",        {}),
        ("page_only",        {"page": page}),
        ("page_take_50",     {"page": page, "take": 50}),
        ("page_take_200",    {"page": page, "take": 200}),
    ]

    results = {**key_info}
    resp = None
    for label, params in combos:
        try:
            resp = requests.get(url, headers=hdrs, params=params, timeout=30)
            data = resp.json()
            count = len(data) if isinstance(data, list) else "not_a_list"
            results[label] = {
                "status": resp.status_code,
                "jobs_count": count,
                "raw_preview": str(data)[:200],
            }
            if isinstance(data, dict):
                results[label]["keys"] = list(data.keys())
        except Exception as e:
            results[label] = {"error": str(e)}

    # Capture any rate-limit / diagnostic response headers from last call
    if resp is not None:
        for h in resp.headers:
            hl = h.lower()
            if any(k in hl for k in ("rate", "limit", "request-id", "retry", "x-")):
                results[f"header_{h}"] = resp.headers[h]

    return results


def raw_submissions_test(job_id: str, date_from: str, date_to: str) -> dict:
    """Test /v1/Jobs/{id}/Submissions with multiple param combos.

    Returns a dict like raw_jobs_page() — one key per combo showing
    status code, count, and a preview.  Use this to find which params
    the Submissions endpoint actually supports.
    """
    base = _base_url()
    url = f"{base}/v1/Jobs/{job_id}/Submissions"
    hdrs = get_headers()
    dates = {
        "fromDate": f"{date_from}T00:00:00",
        "toDate": f"{date_to}T23:59:59",
    }

    combos = [
        ("dates_only",          {**dates}),
        ("dates_take_100",      {**dates, "take": 100}),
        ("dates_take_500",      {**dates, "take": 500}),
        ("dates_take_10000",    {**dates, "take": 10000}),
        ("dates_page_1",        {**dates, "page": 1}),
        ("no_params",           {}),
    ]

    results = {"job_id": job_id}
    for label, params in combos:
        try:
            resp = requests.get(url, headers=hdrs, params=params, timeout=30)
            data = resp.json()
            count = len(data) if isinstance(data, list) else "not_a_list"
            results[label] = {
                "status": resp.status_code,
                "count": count,
                "preview": str(data)[:200],
            }
            # Capture pagination headers
            for h in resp.headers:
                if "paging" in h.lower() or "total" in h.lower():
                    results[label][f"hdr_{h}"] = resp.headers[h]
        except Exception as e:
            results[label] = {"error": str(e)}

    return results


def fetch_submission_detail(submission_id) -> dict:
    """Fetch full detail for a single submission, including answers and photos.

    Endpoint: GET /v1/submissions/{id}?includeAnswers=true&includeQuestions=true

    Returns the raw JSON dict — field structure unknown until first live call.
    Used by the diagnostic button to discover what data the API provides.
    """
    base = _base_url()
    resp = requests.get(
        f"{base}/v1/submissions/{submission_id}",
        headers=get_headers(),
        params={"includeAnswers": "true", "includeQuestions": "true"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_all_jobs() -> list[dict]:
    """Fetch all Roamler jobs in a single call (no pagination params).

    The Roamler Customer API returns all jobs when called without page/take
    parameters.  Passing page= or take= causes the API to return an empty
    list — discovered via the raw inspector diagnostic.
    """
    base = _base_url()
    resp = requests.get(
        f"{base}/v1/Jobs",
        headers=get_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else data.get("jobs", data.get("Jobs", []))


def fetch_submissions(job_id: str, date_from: str = None, date_to: str = None) -> list[dict]:
    """Fetch submissions for a single job within the date window.

    The Submissions endpoint supports ``take`` up to ~500.  Values above
    that (e.g. 10 000) cause the API to return an unparseable response.
    We use take=500 which comfortably covers the largest jobs (~350).
    If a job ever exceeds 500 we paginate with page=2, page=3, etc.
    """
    if date_from is None:
        date_from = _get_secret("ROAMLER_DATE_FROM", "2026-03-09")
    if date_to is None:
        date_to = _get_secret("ROAMLER_DATE_TO", "2026-06-30")

    base = _base_url()
    hdrs = get_headers()
    url = f"{base}/v1/Jobs/{job_id}/Submissions"
    date_params = {
        "fromDate": f"{date_from}T00:00:00",
        "toDate": f"{date_to}T23:59:59",
    }

    # First page — take=500 covers most jobs in a single call
    resp = requests.get(
        url, headers=hdrs,
        params={**date_params, "take": 500},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    results = data if isinstance(data, list) else data.get("submissions", data.get("Submissions", []))

    # Check if there are more than 500 — paginate if needed
    total = int(resp.headers.get("X-Paging-TotalRecordCount", len(results)))
    page = 2
    while len(results) < total:
        resp = requests.get(
            url, headers=hdrs,
            params={**date_params, "take": 500, "page": page},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        batch = data if isinstance(data, list) else data.get("submissions", data.get("Submissions", []))
        if not batch:
            break  # safety valve
        results.extend(batch)
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


def debug_jobs_with_submissions(
    date_from: str,
    date_to: str,
    progress_cb=None,
) -> tuple[list[dict], dict]:
    """Like debug_jobs() but also fetches the submission count for each job.

    progress_cb: optional callable(done: int, total: int) for progress reporting.

    The returned rows each gain a 'submissions' field:
      >=0   = actual submission count
       -1   = skipped (unknown market)
       -2   = HTTP / parse error (see 'sub_error' field)
    """
    rows, meta = debug_jobs()
    if not rows or "error" in meta:
        return rows, meta

    total = len(rows)
    for i, row in enumerate(rows):
        if progress_cb:
            progress_cb(i, total)
        if row["market"] == "??":
            row["submissions"] = -1   # skipped — market unknown
            continue
        try:
            subs = fetch_submissions(row["id"], date_from, date_to)
            row["submissions"] = len(subs)
        except Exception as e:
            row["submissions"] = -2   # error fetching
            row["sub_error"] = str(e)

    if progress_cb:
        progress_cb(total, total)
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

    # Filter to jobs with a known market before fetching submissions.
    valid_jobs = [j for j in jobs if _parse_market(j) != "??"]

    def _fetch_one(job):
        market   = _parse_market(job)
        category = _parse_category(job)
        jid      = _job_id(job)
        try:
            subs = fetch_submissions(jid, date_from, date_to)
            return (market, category), len(subs), None
        except Exception as err:
            return (market, category), 0, f"{jid} ({market}/{category}): {err}"

    # Fetch all jobs in parallel — ~10× faster than sequential for 50+ jobs.
    with ThreadPoolExecutor(max_workers=10) as pool:
        for key, count, error in pool.map(_fetch_one, valid_jobs):
            if error:
                skipped.append(error)
            else:
                counts[key] = counts.get(key, 0) + count

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
