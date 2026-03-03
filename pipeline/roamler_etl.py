"""
Roamler Full ETL — Versuni Mystery Shopping Wave III
====================================================
Fetches ALL submission details from the Roamler API (or loads cached
JSON files), extracts every field needed for the BI dashboard, calculates
KPI scores, and writes a rich master Parquet + Excel file.

Usage:
    python pipeline/roamler_etl.py
    python pipeline/roamler_etl.py --wave 2 --date-from 2025-01-01 --date-to 2025-06-30
    python pipeline/roamler_etl.py --from-cache          # load saved submission JSONs

Output:
    data/processed/master.parquet       (primary — fast for dashboard)
    data/processed/master.xlsx          (secondary — for manual inspection)
    data/raw/submissions_cache/         (per-submission JSON files)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

ROOT        = Path(__file__).parent.parent
CACHE_DIR   = ROOT / "data" / "raw" / "submissions_cache"
PROCESSED   = ROOT / "data" / "processed"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT))
from progress.connectors.roamler import (
    fetch_all_jobs, fetch_submissions, fetch_submission_detail,
    _parse_market, _parse_category, _job_id, is_configured, _get_secret,
)
from pipeline.scoring import get_engine

# ── Constants ─────────────────────────────────────────────────────────────────

MARKET_NAMES = {
    "DE": "Germany", "FR": "France", "NL": "Netherlands",
    "UK": "United Kingdom", "TR": "Turkey",
    "AU": "Australia", "BR": "Brazil", "US": "United States",
}

WAVE_DATE_RANGES = {
    1: ("2024-01-01", "2024-06-30"),
    2: ("2025-01-01", "2025-06-30"),
    3: ("2026-01-01", "2026-06-30"),
}

WAVE_LABELS = {1: "Wave I", 2: "Wave II", 3: "Wave III"}

# All known brands that appear across questionnaires (for facings extraction)
ALL_BRANDS = [
    "Philips", "Delonghi", "Siemens", "Jura", "Smeg", "Miele",
    "Bosch", "Nespresso", "Krups", "Melitta", "Saeco", "Nivona",
    "Gaggia", "Quick Mill", "Magimix", "Sage", "Breville", "Beko",
    "Arçelik", "Arzum", "Baristina", "Fakir", "Grundig", "Braun",
    "Tefal", "Rowenta", "Calor", "Laurastar", "SteamOne", "Steamone",
    "Dyson", "Bissell", "Shark", "Tineco", "Dreame", "Ecovacs",
    "Eufy", "iRobot", "Roborock", "Xiaomi", "MI", "Samsung",
    "Ninja", "Cosori", "Instant", "Princess", "Tower", "Russell Hobbs",
    "Salter", "AEG", "Moulinex", "Seb", "Thomson", "Inventum",
    "Vileda", "Kaercher", "Medek", "Dualit", "Swan", "Solis",
    "Goetze & Jensen", "Blender", "Blaupunkt", "Cecotec",
]


# ── Text normalisers ──────────────────────────────────────────────────────────

def _norm_text(s: str) -> str:
    """Lowercase, collapse whitespace, strip — for fuzzy matching."""
    return " ".join((s or "").split()).lower()


def _extract_brand_from_facings_text(text: str) -> str | None:
    """
    Parse question text like:
      'How many facings of the brand Philips are presented out of packaging...'
      'How many facings does brand Delonghi have in this category? (for boxed...)'
    Returns the brand name or None.
    """
    t = (text or "").strip()
    # Unboxed pattern
    m = re.search(r"facings of (?:the )?brand (.+?) (?:are|have|is|presented)", t, re.I)
    if m:
        return m.group(1).strip().rstrip("?").strip()
    # Boxed pattern
    m = re.search(r"facings does brand (.+?) have", t, re.I)
    if m:
        return m.group(1).strip()
    return None


# ── Per-submission extraction ─────────────────────────────────────────────────

def _extract_submission(
    detail: dict,
    market: str,
    category: str,
    wave_num: int,
    engine,
) -> dict[str, Any]:
    """
    Convert a raw Roamler submission detail dict into a flat row dict.
    All fields needed by any of the 10 dashboard views are extracted here.
    """
    row: dict[str, Any] = {}

    # ── Metadata ──────────────────────────────────────────────────────────────
    sub_id   = detail.get("id") or detail.get("Id") or ""
    job_title = detail.get("jobTitle") or detail.get("workingTitle") or ""

    # Support both camelCase and PascalCase keys (Roamler API is inconsistent)
    loc = detail.get("location") or detail.get("Location") or {}
    raw_attrs = (
        loc.get("attributes") or loc.get("Attributes") or []
    )
    # Build a case-normalised lookup: lowercased name → value
    attrs: dict[str, str] = {}
    for a in raw_attrs:
        name  = str(a.get("name")  or a.get("Name")  or a.get("key")  or a.get("Key")  or "")
        value = str(a.get("value") or a.get("Value") or a.get("val")  or a.get("Val")
                   or a.get("text")  or a.get("Text") or "")
        attrs[name] = value          # original case (for exact lookups)
        attrs[name.lower()] = value  # lowercase (for case-insensitive fallback)

    # ── Address (used for retailer extraction + store_name) ──────────────────
    address = (
        loc.get("address") or loc.get("displayAddress")
        or loc.get("Address") or loc.get("DisplayAddress") or ""
    )
    # Roamler address format: "RetailerName, street, city" — first token is the retailer
    retailer_from_address = address.split(",")[0].strip() if address else ""

    # ── Retailer ──────────────────────────────────────────────────────────────
    # Try known attribute keys first (usually empty in practice), then fall back
    # to parsing the first comma-delimited token of the address field.
    retailer = (
        attrs.get("1Retailer")
        or attrs.get("Retailer")
        or attrs.get("retailer")
        or attrs.get("1retailer")
        or attrs.get("RetailerName")
        or attrs.get("retailername")
        or loc.get("retailer") or loc.get("Retailer")
        or loc.get("name") or loc.get("Name")
        or ""
    )
    if not retailer:
        # Scan all attribute names for "retailer" substring
        for k, v in attrs.items():
            if "retailer" in k.lower() and v:
                retailer = v
                break
    if not retailer:
        # Primary real-world source: first token of address field
        retailer = retailer_from_address

    # ── Price range ───────────────────────────────────────────────────────────
    price_range = ""
    for k, v in attrs.items():
        if any(x in k.lower() for x in ("pricerange", "price_range", "price range")):
            price_range = str(v)
            break
    if not price_range:
        for k, v in attrs.items():
            if "price" in k.lower() and v:
                price_range = str(v)
                break

    row.update({
        "submission_id":  str(sub_id),
        "market":         market,
        "market_name":    MARKET_NAMES.get(market, market),
        "category":       category,
        "retailer":       retailer,
        "store_name":     address,
        "store_id":       str(loc.get("id") or loc.get("Id") or ""),
        "visit_date":     (detail.get("submissionDate") or detail.get("submitDate") or "")[:10],
        "wave":           WAVE_LABELS.get(wave_num, f"Wave {wave_num}"),
        "wave_num":       wave_num,
        "price_range":    price_range,
        "lat":            loc.get("lat") or loc.get("latitude") or None,
        "lng":            loc.get("lng") or loc.get("longitude") or None,
    })

    # ── Build answer lookup: question_id → answer dict ───────────────────────
    questions = detail.get("questions") or detail.get("Questions") or []
    answers   = detail.get("answers")   or detail.get("Answers")   or []

    # Build question ID → code map from submission's own questions list
    qid2code: dict[int, str] = {}
    qid2text: dict[int, str] = {}
    for q in questions:
        qid  = q.get("id") or q.get("Id")
        qcode = q.get("code") or q.get("Code") or ""
        qtext = q.get("text") or q.get("Text") or ""
        if qid:
            qid2code[int(qid)] = qcode
            qid2text[int(qid)] = qtext

    # Build answer lookup: question_code → answer dict
    code2ans: dict[str, dict] = {}
    for ans in answers:
        qid = ans.get("questionId") or ans.get("QuestionId")
        if qid is None:
            continue
        qid = int(qid)
        qcode = qid2code.get(qid, "")
        if qcode:
            code2ans[qcode] = ans

    # Helper: get selected answer option texts for a question code
    def selected_texts(qcode: str) -> list[str]:
        ans = code2ans.get(qcode, {})
        opts = ans.get("answerOptions") or ans.get("AnswerOptions") or []
        return [o.get("text") or o.get("Text") or "" for o in opts if o.get("text") or o.get("Text")]

    def selected_codes(qcode: str) -> list[str]:
        ans = code2ans.get(qcode, {})
        opts = ans.get("answerOptions") or ans.get("AnswerOptions") or []
        return [o.get("code") or o.get("Code") or "" for o in opts]

    def answer_text(qcode: str) -> str:
        ans = code2ans.get(qcode, {})
        return (ans.get("text") or ans.get("Text") or "").strip()

    def answer_value(qcode: str) -> Any:
        ans = code2ans.get(qcode, {})
        return ans.get("value") or ans.get("Value")

    # ── KPI Scores ────────────────────────────────────────────────────────────
    scores = engine.score_submission(answers, category, questions)
    row.update(scores)

    # ── KPI1 — Availability detail ────────────────────────────────────────────
    # Category present  (Q_KPI1_Score_Q49 for FAEM; Q_KPI1_Score_Q1 for Airfryer etc.)
    cat_present_code = next(
        (c for c in code2ans if re.match(r"Q_KPI1_Score_Q\d+", c)
         and any("available" in t.lower() or "aanwezig" in t.lower()
                 for t in selected_texts(c) + [qid2text.get(
                     next((qid for qid, cd in qid2code.items() if cd == c), 0), "")])),
        None
    )
    # Simpler: look for Q_KPI1_Score_Q49 first, then Q1
    for candidate in ("Q_KPI1_Score_Q49", "Q_KPI1_Score_Q1",
                       "Q_KPI1_Score_Q50", "Q_KPI1_Score_Q2"):
        if candidate in code2ans:
            cat_present_code = candidate
            break

    cat_present_texts = selected_texts(cat_present_code or "")
    row["kpi1_category_present"] = bool(
        cat_present_texts and any("yes" in t.lower() for t in cat_present_texts)
    )

    # Brands available on shelf (multi-select, Q_KPI1_Score_Q50 / Q2)
    brands_on_shelf_code = next(
        (c for c in ("Q_KPI1_Score_Q50", "Q_KPI1_Score_Q2", "Q_KPI1_Score_Q3")
         if c in code2ans), None
    )
    row["kpi1_brands_available"] = "|".join(selected_texts(brands_on_shelf_code or ""))

    # Philips several models unboxed (Q56 for FAEM, Q8 for Airfryer etc.)
    philips_models_code = next(
        (c for c in ("Q_KPI1_Score_Q56", "Q_KPI1_Score_Q8") if c in code2ans), None
    )
    pm_texts = selected_texts(philips_models_code or "")
    row["kpi1_philips_unboxed_models"] = bool(pm_texts and any("yes" in t.lower() for t in pm_texts))

    # Philips boxed stock (Q51)
    pb_code = next((c for c in ("Q_KPI1_Score_Q51", "Q_KPI1_Score_Q5") if c in code2ans), None)
    pb_texts = selected_texts(pb_code or "")
    row["kpi1_philips_boxed_stock"] = bool(pb_texts and any("yes" in t.lower() for t in pb_texts))

    # 2nd placement Philips (Q54 for FAEM, Q6 for others)
    snd_code = next((c for c in ("Q_KPI1_Score_Q54", "Q_KPI1_Score_Q6") if c in code2ans), None)
    snd_texts = selected_texts(snd_code or "")
    row["kpi1_philips_2nd_placement"] = bool(snd_texts and any("yes" in t.lower() for t in snd_texts))

    # Brands on promo (Q53 for FAEM, Q3 for others)
    promo_code = next((c for c in ("Q_KPI1_Score_Q53", "Q_KPI1_Score_Q3") if c in code2ans), None)
    row["kpi1_brands_on_promo"] = "|".join(selected_texts(promo_code or ""))

    # Philips available (derived: either on shelf OR boxed stock)
    brands_available_text = row.get("kpi1_brands_available", "")
    row["kpi1_philips_available"] = (
        "philips" in brands_available_text.lower()
        or row["kpi1_philips_boxed_stock"]
        or row["kpi1_philips_unboxed_models"]
    )

    # ── Facings — unboxed (per brand from numeric answer questions) ───────────
    for q in questions:
        qtext = q.get("text") or q.get("Text") or ""
        qcode = q.get("code") or q.get("Code") or ""
        if ("facings" not in qtext.lower()
                or "out of packaging" not in qtext.lower()
                or not qcode):
            continue
        brand = _extract_brand_from_facings_text(qtext)
        if not brand:
            continue
        brand_key = "facings_unboxed_" + re.sub(r"[^a-z0-9]", "_", brand.lower()).strip("_")
        val = answer_value(qcode)
        try:
            row[brand_key] = int(val) if val is not None else 0
        except (ValueError, TypeError):
            row[brand_key] = 0

    # ── Facings — boxed ────────────────────────────────────────────────────────
    for q in questions:
        qtext = q.get("text") or q.get("Text") or ""
        qcode = q.get("code") or q.get("Code") or ""
        if ("facings" not in qtext.lower()
                or "boxed" not in qtext.lower()
                or not qcode):
            continue
        brand = _extract_brand_from_facings_text(qtext)
        if not brand:
            continue
        brand_key = "facings_boxed_" + re.sub(r"[^a-z0-9]", "_", brand.lower()).strip("_")
        val = answer_value(qcode)
        try:
            row[brand_key] = int(val) if val is not None else 0
        except (ValueError, TypeError):
            row[brand_key] = 0

    # ── KPI2 — Visibility detail ───────────────────────────────────────────────
    # Top-4 eye-catching brands
    eyecatch_code = next(
        (c for c in ("Q_KPI2_Score_Q26", "Q_KPI2_Score_Q2") if c in code2ans), None
    )
    row["kpi2_eyecatching_brands"] = "|".join(selected_texts(eyecatch_code or ""))

    # Most standout brand
    standout_code = next(
        (c for c in ("Q_KPI2_Score_Q27", "Q_KPI2_Score_Q3") if c in code2ans), None
    )
    standout_texts = selected_texts(standout_code or "")
    row["kpi2_standout_brand"] = standout_texts[0] if standout_texts else ""

    # Standout reason (free text or multi-select on next question)
    # Look for a question about "why" near the standout question in sequence
    standout_reason_code = next(
        (c for c in code2ans
         if "reason" in (qid2text.get(
             next((qid for qid, cd in qid2code.items() if cd == c), 0), "")).lower()
         or "why" in (qid2text.get(
             next((qid for qid, cd in qid2code.items() if cd == c), 0), "")).lower()
        ), None
    )
    if standout_reason_code:
        reasons = selected_texts(standout_reason_code)
        row["kpi2_standout_reason"] = "|".join(reasons)
    else:
        row["kpi2_standout_reason"] = ""

    # Philips models grouped (Q28, Q4)
    grouped_code = next(
        (c for c in ("Q_KPI2_Score_Q28", "Q_KPI2_Score_Q4") if c in code2ans), None
    )
    grouped_texts = selected_texts(grouped_code or "")
    row["kpi2_philips_grouped"] = bool(
        grouped_texts and any("yes" in t.lower() for t in grouped_texts)
    )

    # ── KPI3 — Recommendation detail ──────────────────────────────────────────
    # 1st recommended brand
    rec1_code = next(
        (c for c in ("Q_KPI3_Score_Q13", "Q_KPI3_Score_Q1") if c in code2ans), None
    )
    rec1_texts = selected_texts(rec1_code or "")
    row["kpi3_1st_recommended_brand"] = rec1_texts[0] if rec1_texts else ""

    # Recommendation reasons — look for question after rec1 about reasons
    # These are typically multi-select and not KPI-scored
    rec1_reasons: list[str] = []
    for q in questions:
        qcode = q.get("code") or q.get("Code") or ""
        if qcode in code2ans and qcode not in (
            "Q_KPI3_Score_Q13", "Q_KPI3_Score_Q1",
            "Q_KPI3_Score_Q14", "Q_KPI3_Score_Q2",
        ):
            qtext = (q.get("text") or q.get("Text") or "").lower()
            if "recommend" in qtext and "reason" in qtext:
                rec1_reasons = selected_texts(qcode)
                break
    row["kpi3_1st_recommendation_reason"] = "|".join(rec1_reasons)

    # 2nd recommended brand
    rec2_code = next(
        (c for c in ("Q_KPI3_Score_Q14", "Q_KPI3_Score_Q2") if c in code2ans), None
    )
    rec2_texts = selected_texts(rec2_code or "")
    row["kpi3_2nd_recommended_brand"] = rec2_texts[0] if rec2_texts else ""

    return row


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_path(submission_id: str, wave_num: int) -> Path:
    return CACHE_DIR / f"w{wave_num}_{submission_id}.json"


def _load_cached(submission_id: str, wave_num: int) -> dict | None:
    p = _cache_path(submission_id, wave_num)
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return None


def _save_cached(submission_id: str, wave_num: int, detail: dict) -> None:
    p = _cache_path(submission_id, wave_num)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(detail, f)


# ── Main ETL logic ────────────────────────────────────────────────────────────

def fetch_and_extract(
    wave_nums: list[int] | None = None,
    from_cache: bool = False,
    max_workers: int = 8,
    limit: int | None = None,
) -> pd.DataFrame:
    """
    Full ETL: fetch submissions for the requested waves and extract all fields.

    Parameters
    ----------
    wave_nums : list[int], default [1, 2, 3]
        Which waves to fetch (1 = 2024, 2 = 2025, 3 = 2026).
    from_cache : bool
        If True, load only previously cached submission JSONs (no API calls).
    max_workers : int
        Thread pool size for parallel API calls.
    limit : int | None
        If set, only process this many submissions per wave (for testing).

    Returns
    -------
    pd.DataFrame with all extracted rows.
    """
    if wave_nums is None:
        wave_nums = [1, 2, 3]

    engine = get_engine()
    all_rows: list[dict] = []

    if from_cache:
        # Load all cached files
        for cache_file in sorted(CACHE_DIR.glob("*.json")):
            stem = cache_file.stem  # e.g. "w2_12345678"
            parts = stem.split("_", 1)
            wave_num = int(parts[0][1:]) if parts[0].startswith("w") else 2
            if wave_num not in wave_nums:
                continue
            with open(cache_file, encoding="utf-8") as f:
                detail = json.load(f)
            market   = detail.get("_market", "??")
            category = detail.get("_category", "??")
            row = _extract_submission(detail, market, category, wave_num, engine)
            all_rows.append(row)
        print(f"  Loaded {len(all_rows)} submissions from cache.")
        return pd.DataFrame(all_rows)

    # Live API fetch
    if not is_configured():
        print("  ⚠ Roamler API not configured — no data fetched.")
        return pd.DataFrame()

    for wave_num in wave_nums:
        date_from, date_to = WAVE_DATE_RANGES[wave_num]
        print(f"\n─── Wave {wave_num} ({date_from} → {date_to}) ───")

        jobs = fetch_all_jobs()
        print(f"  Found {len(jobs)} jobs total")

        # Collect all (job_meta, submission_stub) pairs
        job_submissions: list[tuple[dict, dict, str, str]] = []  # (job, sub, market, category)
        for job in jobs:
            market   = _parse_market(job)
            category = _parse_category(job)
            if market == "??":
                continue
            jid = _job_id(job)
            try:
                subs = fetch_submissions(jid, date_from, date_to)
            except Exception as e:
                print(f"    SKIP {market}/{category}: {e}")
                continue
            for s in subs:
                job_submissions.append((job, s, market, category))
            if subs:
                print(f"    {market}/{category}: {len(subs)} submissions")

        if limit:
            job_submissions = job_submissions[:limit]
            print(f"  ⚠ Limit applied — processing only {limit} submissions")

        print(f"  Fetching details for {len(job_submissions)} submissions…")

        def _fetch_detail(args):
            job, sub, market, category = args
            sub_id = str(sub.get("id") or sub.get("Id") or sub.get("hRef", "").split("/")[-1])
            cached = _load_cached(sub_id, wave_num)
            if cached:
                detail = cached
            else:
                try:
                    detail = fetch_submission_detail(sub_id)
                    detail["_market"]   = market
                    detail["_category"] = category
                    _save_cached(sub_id, wave_num, detail)
                except Exception as e:
                    return None, str(e)
            try:
                row = _extract_submission(detail, market, category, wave_num, engine)
                return row, None
            except Exception as e:
                return None, f"extract error: {e}"

        done = 0
        errors = 0
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_fetch_detail, args): args for args in job_submissions}
            for future in as_completed(futures):
                row, err = future.result()
                done += 1
                if err:
                    errors += 1
                    print(f"    ⚠ [{errors}] {err}")
                elif row:
                    all_rows.append(row)
                if done % 100 == 0:
                    print(f"    … {done}/{len(job_submissions)} done ({errors} errors)")

        print(f"  Wave {wave_num}: {done} processed, {errors} errors, {done - errors} rows added")

    return pd.DataFrame(all_rows)


def run_etl(
    wave_nums: list[int] | None = None,
    from_cache: bool = False,
    max_workers: int = 8,
    limit: int | None = None,
    output_excel: bool = True,
) -> pd.DataFrame:
    """Run the full ETL and save output files."""
    print("\n=== Versuni MS — Roamler Full ETL ===\n")
    df = fetch_and_extract(
        wave_nums=wave_nums,
        from_cache=from_cache,
        max_workers=max_workers,
        limit=limit,
    )

    if df.empty:
        print("  ⚠ No data extracted.")
        return df

    # Coerce types
    for col in ["kpi1_score", "kpi2_score", "kpi3_score", "total_score"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["kpi1_category_present", "kpi1_philips_available",
                "kpi1_philips_unboxed_models", "kpi1_philips_boxed_stock",
                "kpi1_philips_2nd_placement", "kpi2_philips_grouped"]:
        if col in df.columns:
            df[col] = df[col].fillna(False).astype(bool)

    # Ensure visit_date is date
    if "visit_date" in df.columns:
        df["visit_date"] = pd.to_datetime(df["visit_date"], errors="coerce")

    # Sort
    sort_cols = [c for c in ["wave_num", "market", "category", "visit_date"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols).reset_index(drop=True)

    # Save
    parquet_path = PROCESSED / "master.parquet"
    df.to_parquet(parquet_path, index=False)
    print(f"\n  ✓ Saved Parquet → {parquet_path}  ({len(df):,} rows, {len(df.columns)} columns)")

    if output_excel:
        excel_path = PROCESSED / "master.xlsx"
        df.to_excel(excel_path, index=False)
        print(f"  ✓ Saved Excel  → {excel_path}")

    print(f"\n  Waves:    {df['wave'].unique().tolist() if 'wave' in df.columns else '?'}")
    print(f"  Markets:  {sorted(df['market'].unique().tolist()) if 'market' in df.columns else '?'}")
    print(f"  Rows:     {len(df):,}")
    return df


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Versuni Roamler Full ETL")
    parser.add_argument(
        "--wave", "-w", type=int, nargs="+", default=None,
        help="Which wave(s) to fetch: 1, 2, 3. Default: all."
    )
    parser.add_argument(
        "--date-from", default=None,
        help="Override start date (YYYY-MM-DD). Only used with a single wave."
    )
    parser.add_argument(
        "--date-to", default=None,
        help="Override end date (YYYY-MM-DD). Only used with a single wave."
    )
    parser.add_argument(
        "--from-cache", action="store_true",
        help="Load only previously cached submission JSONs (no API calls)."
    )
    parser.add_argument(
        "--workers", type=int, default=8,
        help="Thread pool size for parallel API calls (default: 8)."
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Process only this many submissions (for testing)."
    )
    parser.add_argument(
        "--no-excel", action="store_true",
        help="Skip writing the Excel file (only write Parquet)."
    )
    args = parser.parse_args()

    wave_nums = args.wave if args.wave else None

    # Handle custom date range override for single-wave mode
    if args.date_from or args.date_to:
        if wave_nums and len(wave_nums) == 1:
            wn = wave_nums[0]
            orig_from, orig_to = WAVE_DATE_RANGES[wn]
            WAVE_DATE_RANGES[wn] = (
                args.date_from or orig_from,
                args.date_to   or orig_to,
            )
        else:
            print("--date-from/--date-to only supported with a single --wave.")

    run_etl(
        wave_nums=wave_nums,
        from_cache=args.from_cache,
        max_workers=args.workers,
        limit=args.limit,
        output_excel=not args.no_excel,
    )


if __name__ == "__main__":
    main()
