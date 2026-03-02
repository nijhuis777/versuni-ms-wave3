"""
Dashboard Data Loader — Versuni Mystery Shopping
================================================
Single source of truth for loading master data into the dashboard.
Handles Parquet loading, fallback to demo data, and caching.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

PARQUET_PATH = ROOT / "data" / "processed" / "master.parquet"
EXCEL_PATH   = ROOT / "data" / "processed" / "master.xlsx"

MARKET_NAMES = {
    "DE": "Germany", "FR": "France", "NL": "Netherlands",
    "UK": "United Kingdom", "TR": "Turkey",
    "AU": "Australia", "BR": "Brazil", "US": "United States",
}

WAVE_ORDER = ["Wave I", "Wave II", "Wave III"]

KPI_COLORS = {
    "total_score":  "#FF6738",   # Roamler orange
    "kpi1_score":   "#003087",   # Versuni blue
    "kpi2_score":   "#4CAF50",   # green
    "kpi3_score":   "#0075BE",   # light blue
}

KPI_LABELS = {
    "total_score":  "Total Score",
    "kpi1_score":   "Brand Availability",
    "kpi2_score":   "Brand Visibility",
    "kpi3_score":   "Brand Recommendation",
}


# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def _load_master_cached(parquet_mtime: float, excel_mtime: float) -> tuple[pd.DataFrame, bool]:
    """
    Internal cached loader.  parquet_mtime / excel_mtime are used as
    cache-bust keys so the cache auto-invalidates whenever the ETL
    writes a new file.
    """
    if PARQUET_PATH.exists():
        df = pd.read_parquet(PARQUET_PATH)
        _ensure_types(df)
        return df, False

    if EXCEL_PATH.exists():
        df = pd.read_excel(EXCEL_PATH)
        _ensure_types(df)
        return df, False

    return _demo_data(), True


def load_master() -> tuple[pd.DataFrame, bool]:
    """
    Load master dataset from Parquet (preferred) or Excel.
    Returns (df, is_demo) where is_demo=True when no real data exists.
    Cache auto-invalidates whenever the ETL writes a new file.
    """
    pm = PARQUET_PATH.stat().st_mtime if PARQUET_PATH.exists() else 0.0
    em = EXCEL_PATH.stat().st_mtime   if EXCEL_PATH.exists()   else 0.0
    return _load_master_cached(pm, em)


def _ensure_types(df: pd.DataFrame) -> None:
    """Coerce column types in-place."""
    score_cols = [c for c in df.columns if c.endswith("_score")]
    for col in score_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    bool_cols = [
        "kpi1_category_present", "kpi1_philips_available",
        "kpi1_philips_unboxed_models", "kpi1_philips_boxed_stock",
        "kpi1_philips_2nd_placement", "kpi2_philips_grouped",
    ]
    for col in bool_cols:
        if col in df.columns:
            df[col] = df[col].fillna(False).astype(bool)

    if "visit_date" in df.columns:
        df["visit_date"] = pd.to_datetime(df["visit_date"], errors="coerce")

    if "wave_num" not in df.columns and "wave" in df.columns:
        wave_map = {"Wave I": 1, "Wave II": 2, "Wave III": 3}
        df["wave_num"] = df["wave"].map(wave_map)

    if "market_name" not in df.columns and "market" in df.columns:
        df["market_name"] = df["market"].map(MARKET_NAMES).fillna(df["market"])


def _demo_data() -> pd.DataFrame:
    """Realistic demo data for development / before real data arrives."""
    import random
    random.seed(42)

    markets    = ["DE", "FR", "NL", "UK", "TR"]
    categories = ["FAEM", "SAEM", "Airfryer", "Handstick_Dry", "Handheld_Steamer", "RVC"]
    waves      = [("Wave I", 1, "2024"), ("Wave II", 2, "2025"), ("Wave III", 3, "2026")]
    retailers  = {
        "DE": ["MediaMarkt", "Saturn", "Expert", "Euronics"],
        "FR": ["Fnac", "Boulanger", "Darty", "Leclerc"],
        "NL": ["MediaMarkt", "Expert", "Coolblue", "Blokker"],
        "UK": ["Currys", "John Lewis", "Argos"],
        "TR": ["Teknosa", "MediaMarkt", "Bimeks"],
    }
    brands = ["Philips", "Delonghi", "Siemens", "Tefal", "Bosch",
              "Ninja", "Dyson", "Shark", "Other"]
    price_ranges = ["Low", "Medium", "High"]

    rows = []
    wave_trend = {1: 0.85, 2: 1.0, 3: 1.08}  # scores improve wave over wave

    for wave_label, wave_num, year in waves:
        factor = wave_trend[wave_num]
        for market in markets:
            n_cats = {"DE": 5, "FR": 4, "NL": 5, "UK": 4, "TR": 5}.get(market, 4)
            n_stores = {"DE": 30, "FR": 25, "NL": 20, "UK": 25, "TR": 25}.get(market, 20)
            for cat in categories[:n_cats]:
                for i in range(n_stores):
                    retailer = random.choice(retailers.get(market, ["Unknown"]))
                    cat_present = random.random() > 0.08
                    philips_avail = cat_present and random.random() > 0.15
                    kpi1 = min(100, round(random.uniform(40, 70) * factor, 1))
                    kpi2 = min(100, round(random.uniform(35, 65) * factor, 1))
                    kpi3 = min(100, round(random.uniform(20, 50) * factor, 1))
                    total = round((kpi1 + kpi2 + kpi3) / 3, 1)

                    rows.append({
                        "submission_id":              f"demo_{wave_num}_{market}_{cat}_{i}",
                        "market":                     market,
                        "market_name":                MARKET_NAMES[market],
                        "category":                   cat,
                        "retailer":                   retailer,
                        "store_name":                 f"{retailer}; Demo Store {i+1}, {MARKET_NAMES[market]}",
                        "store_id":                   f"store_{i:04d}",
                        "visit_date":                 pd.Timestamp(f"{year}-0{random.randint(1,6)}-{random.randint(1,28):02d}"),
                        "wave":                       wave_label,
                        "wave_num":                   wave_num,
                        "price_range":                random.choice(price_ranges),
                        "kpi1_score":                 kpi1,
                        "kpi2_score":                 kpi2,
                        "kpi3_score":                 kpi3,
                        "total_score":                total,
                        "kpi1_category_present":      cat_present,
                        "kpi1_philips_available":     philips_avail,
                        "kpi1_philips_unboxed_models": philips_avail and random.random() > 0.3,
                        "kpi1_philips_boxed_stock":   philips_avail and random.random() > 0.4,
                        "kpi1_philips_2nd_placement": philips_avail and random.random() > 0.6,
                        "kpi1_brands_available":      "|".join(random.sample(brands[:6], k=random.randint(2, 5))),
                        "kpi1_brands_on_promo":       "|".join(random.sample(brands[:4], k=random.randint(0, 2))),
                        "kpi2_eyecatching_brands":    "|".join(random.sample(brands, k=4)),
                        "kpi2_standout_brand":        random.choice(brands[:6]),
                        "kpi2_standout_reason":       random.choice([
                            "Attractiveness of the machines (e.g. striking colours/design)",
                            "Highest number of products available",
                            "Signs/ brand logo",
                            "Largest display/secondary display in this category",
                            "Placement close to the aisle",
                        ]),
                        "kpi2_philips_grouped":       random.random() > 0.4,
                        "kpi3_1st_recommended_brand": random.choice(["Philips"] * 3 + brands[1:5]),
                        "kpi3_1st_recommendation_reason": random.choice([
                            "Price / Quality Ratio",
                            "Design",
                            "Quality (less complains/ services)",
                            "Easy to use",
                            "Experienced brand in this field",
                        ]),
                        "kpi3_2nd_recommended_brand": random.choice(brands[1:6]),
                        "facings_unboxed_philips":    random.randint(0, 8) if philips_avail else 0,
                        "facings_unboxed_delonghi":   random.randint(0, 6),
                        "facings_unboxed_siemens":    random.randint(0, 5),
                        "facings_unboxed_bosch":      random.randint(0, 4),
                        "facings_unboxed_nespresso":  random.randint(0, 4),
                        "facings_unboxed_other":      random.randint(0, 3),
                        "facings_boxed_philips":      random.randint(0, 5) if philips_avail else 0,
                        "facings_boxed_delonghi":     random.randint(0, 4),
                        "facings_boxed_siemens":      random.randint(0, 4),
                    })

    df = pd.DataFrame(rows)
    return df


# ── Filter helpers ────────────────────────────────────────────────────────────

def apply_filters(
    df: pd.DataFrame,
    waves: list[str],
    markets: list[str],
    categories: list[str],
    retailers: list[str],
    price_ranges: list[str] | None = None,
) -> pd.DataFrame:
    mask = pd.Series(True, index=df.index)
    if waves and "wave" in df.columns:
        mask &= df["wave"].isin(waves)
    if markets and "market_name" in df.columns:
        mask &= df["market_name"].isin(markets)
    if categories and "category" in df.columns:
        mask &= df["category"].isin(categories)
    if retailers and "retailer" in df.columns:
        mask &= df["retailer"].isin(retailers)
    if price_ranges and "price_range" in df.columns:
        mask &= df["price_range"].isin(price_ranges)
    return df[mask].copy()


def _fix_multiselect_state(key: str, valid_options: list) -> None:
    """Keep session-state for a multiselect in sync with the available options.
    On first visit initialise to all options; on subsequent visits drop any
    value that is no longer in the (narrowed) option list.
    """
    if key not in st.session_state:
        st.session_state[key] = valid_options
    else:
        kept = [v for v in st.session_state[key] if v in valid_options]
        st.session_state[key] = kept if kept else valid_options


def sidebar_filters(df: pd.DataFrame, key_prefix: str = "") -> dict:
    """
    Render cascading filters as a top-bar horizontal row.
    Each filter's options narrow based on upstream selections.
    Selections persist across view/tab changes via session state.
    Returns a dict of filter values for use with apply_filters().
    """
    # ── Wave (anchored to full df) ─────────────────────────────────────────
    waves_avail = [w for w in WAVE_ORDER if "wave" in df.columns and w in df["wave"].unique()]
    if not waves_avail:
        waves_avail = list(df["wave"].dropna().unique()) if "wave" in df.columns else WAVE_ORDER

    wave_key = f"{key_prefix}wave"
    _fix_multiselect_state(wave_key, waves_avail)
    cur_waves = st.session_state[wave_key]

    # ── Narrow df by wave → derive Country options ─────────────────────────
    df_w = df[df["wave"].isin(cur_waves)] if (cur_waves and "wave" in df.columns) else df
    markets_avail = sorted(df_w["market_name"].dropna().unique()) if "market_name" in df_w.columns else []

    market_key = f"{key_prefix}market"
    _fix_multiselect_state(market_key, markets_avail)
    cur_markets = st.session_state[market_key]

    # ── Narrow by Country → derive Category options ────────────────────────
    df_wm = df_w[df_w["market_name"].isin(cur_markets)] if (cur_markets and "market_name" in df_w.columns) else df_w
    cats_avail = sorted(df_wm["category"].dropna().unique()) if "category" in df_wm.columns else []

    cat_key = f"{key_prefix}category"
    _fix_multiselect_state(cat_key, cats_avail)
    cur_cats = st.session_state[cat_key]

    # ── Narrow by Category → derive Retailer options ───────────────────────
    df_wmc = df_wm[df_wm["category"].isin(cur_cats)] if (cur_cats and "category" in df_wm.columns) else df_wm
    retailers_avail = sorted(
        r for r in (df_wmc["retailer"].dropna().unique() if "retailer" in df_wmc.columns else [])
        if r and str(r).strip()
    )

    retailer_key = f"{key_prefix}retailer"
    _fix_multiselect_state(retailer_key, retailers_avail)
    cur_retailers = st.session_state[retailer_key]

    # ── Narrow by Retailer → derive Price Range options ────────────────────
    df_wmcr = df_wmc[df_wmc["retailer"].isin(cur_retailers)] if (cur_retailers and "retailer" in df_wmc.columns) else df_wmc
    pr_avail = [p for p in ["Low", "Medium", "High"]
                if "price_range" in df_wmcr.columns and p in df_wmcr["price_range"].values]

    pr_key = f"{key_prefix}price_range"
    if pr_avail:
        _fix_multiselect_state(pr_key, pr_avail)
        cur_pr = st.session_state[pr_key]
    else:
        cur_pr = []

    # ── Render ─────────────────────────────────────────────────────────────
    has_price = bool(pr_avail)
    cols = st.columns(5 if has_price else 4)

    with cols[0]:
        waves = st.multiselect("🌊 Wave", options=waves_avail, key=wave_key)
    with cols[1]:
        markets = st.multiselect("🌍 Country", options=markets_avail, key=market_key)
    with cols[2]:
        categories = st.multiselect("📦 Category", options=cats_avail, key=cat_key)
    with cols[3]:
        retailers = st.multiselect("🏪 Retailer", options=retailers_avail, key=retailer_key)
    if has_price:
        with cols[4]:
            price_ranges = st.multiselect("💰 Price Range", options=pr_avail, key=pr_key)
    else:
        price_ranges = []

    st.divider()

    return {
        "waves": waves,
        "markets": markets,
        "categories": categories,
        "retailers": retailers,
        "price_ranges": price_ranges,
    }


# ── Chart helpers ──────────────────────────────────────────────────────────────

def score_color(value: float) -> str:
    """Return a hex color based on score (red < 40, amber < 70, green ≥ 70)."""
    if value >= 70:
        return "#4CAF50"
    if value >= 40:
        return "#FF9800"
    return "#E53935"


def n_visits_caption(df: pd.DataFrame) -> str:
    mkt = df["market"].nunique() if "market" in df.columns else "?"
    cat = df["category"].nunique() if "category" in df.columns else "?"
    ret = df["retailer"].nunique() if "retailer" in df.columns else "?"
    waves = "|".join(sorted(df["wave"].dropna().unique())) if "wave" in df.columns else "?"
    return f"n = {len(df):,} visits · {mkt} markets · {cat} categories · {ret} retailers · {waves}"
