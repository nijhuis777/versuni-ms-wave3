"""
Data Pipeline — Versuni MS Wave III
====================================
Pulls raw data from all platforms, harmonizes to a canonical model,
runs quality checks, and outputs a clean master dataset.

Usage:
    python pipeline/etl.py --output data/processed/master_wave3.xlsx
    python pipeline/etl.py --source roamler --market DE
    python pipeline/etl.py --check-only  # run QC without writing output
"""

import json
import argparse
import os
from pathlib import Path
from datetime import datetime

import pandas as pd
import yaml
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)

# ─── Canonical column model ──────────────────────────────────────────────────
CANONICAL_COLUMNS = [
    "market",           # DE, FR, NL, UK, TR, AU, BR, US
    "market_name",      # Germany, France, etc.
    "category",         # FAEM, SAEM, Airfryer, etc.
    "platform",         # roamler, wiser, pinion
    "store_id",         # platform-specific store identifier
    "store_name",       # store name
    "retailer",         # Mediamarkt, Amazon, etc.
    "visit_date",       # YYYY-MM-DD
    "shopper_id",       # anonymized shopper identifier
    "wave",             # "Wave III"

    # KPI1 — Availability
    "kpi1_category_present",        # bool: is the category available in store?
    "kpi1_versuni_brand_present",   # bool: is Philips/Versuni brand available?
    "kpi1_versuni_models_count",    # int: number of Versuni models on display
    "kpi1_versuni_facings_unboxed", # int: unboxed facing count
    "kpi1_versuni_facings_boxed",   # int: boxed facing count
    "kpi1_competitor_brands",       # list/str: which competitor brands are present
    "kpi1_score",                   # float 0–100: calculated KPI1 score

    # KPI2 — Visibility / Attractiveness
    "kpi2_top4_eyecatching",        # list/str: top 4 eye-catching brands
    "kpi2_most_standout",           # str: single most standout brand
    "kpi2_standout_reason",         # list/str: reasons why brand stood out
    "kpi2_versuni_grouped",         # bool: are Versuni models grouped together?
    "kpi2_score",                   # float 0–100

    # KPI3 — Recommendation
    "kpi3_recommended_brand",       # str: brand shopper would recommend
    "kpi3_recommendation_reason",   # str
    "kpi3_score",                   # float 0–100

    "raw_response_id",              # original platform response ID (for traceability)
    "notes",                        # free-text notes from shopper or QC
]

MARKET_NAMES = {
    "DE": "Germany", "FR": "France", "NL": "Netherlands",
    "UK": "United Kingdom", "TR": "Turkey",
    "AU": "Australia", "BR": "Brazil", "US": "United States",
}

# ─── Platform extractors ─────────────────────────────────────────────────────

def extract_roamler(market: str | None = None) -> pd.DataFrame:
    """
    Pull data from Roamler API or load from cached raw export.
    Maps Roamler's field names → canonical model.
    """
    import requests
    api_key = os.getenv("ROAMLER_API_KEY", "")
    base_url = os.getenv("ROAMLER_API_BASE_URL", "")

    # Try loading from raw file first (offline/batch mode)
    raw_files = list(RAW_DIR.glob("roamler_*.xlsx"))
    if raw_files:
        print(f"  Loading Roamler from {len(raw_files)} raw file(s)...")
        dfs = []
        for f in raw_files:
            df_raw = pd.read_excel(f)
            dfs.append(_map_roamler(df_raw))
        df = pd.concat(dfs, ignore_index=True)
    elif api_key and base_url:
        print("  Pulling from Roamler API...")
        headers = {"Authorization": f"Bearer {api_key}"}
        params = {"wave": "wave3_2026"}
        if market:
            params["market"] = market
        resp = requests.get(f"{base_url}/v1/submissions", headers=headers, params=params, timeout=60)
        resp.raise_for_status()
        df_raw = pd.DataFrame(resp.json().get("submissions", []))
        df = _map_roamler(df_raw)
    else:
        print("  ⚠ No Roamler data source available — returning empty frame")
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    if market:
        df = df[df["market"] == market]
    return df


def _map_roamler(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Map Roamler column names to canonical model."""
    df = pd.DataFrame()

    # These mappings will be refined once we have actual Roamler export headers
    # Using KPI question codes from the FAEM.json as reference
    col_map = {
        "market_code":          "market",
        "category_code":        "category",
        "store_id":             "store_id",
        "store_name":           "store_name",
        "retailer_name":        "retailer",
        "submission_date":      "visit_date",
        "user_id":              "shopper_id",
        "submission_id":        "raw_response_id",
        "Q_KPI1_Score_Q49":     "kpi1_category_present",
        "Q_KPI1_Score_Q50":     "kpi1_competitor_brands",
        "Q_KPI1_Score_Q51":     "kpi1_versuni_brand_present",
        "Q_KPI1_Score_Q56":     "kpi1_versuni_models_count",
        "Q_KPI2_Score_Q26":     "kpi2_top4_eyecatching",
        "Q_KPI2_Score_Q27":     "kpi2_most_standout",
        "Q_KPI2_Score_Q28":     "kpi2_versuni_grouped",
        "Q_KPI3_Score_Q13":     "kpi3_recommended_brand",
        "Q_KPI3_Score_Q14":     "kpi3_recommendation_reason",
    }

    for raw_col, canonical_col in col_map.items():
        if raw_col in df_raw.columns:
            df[canonical_col] = df_raw[raw_col]

    df["platform"] = "roamler"
    df["wave"] = "Wave III"
    df["market_name"] = df.get("market", pd.Series()).map(MARKET_NAMES)

    # Ensure all canonical columns exist
    for col in CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = None

    return df[CANONICAL_COLUMNS]


def extract_wiser() -> pd.DataFrame:
    """Load Wiser data (AU + US) from raw file or API."""
    raw_files = sorted(RAW_DIR.glob("wiser_*.xlsx")) + sorted(RAW_DIR.glob("wiser_*.csv"))

    if not raw_files:
        print("  ⚠ No Wiser raw files found in data/raw/ — returning empty frame")
        print("    Place Wiser exports as wiser_AU_*.xlsx or wiser_US_*.xlsx")
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    dfs = []
    for f in raw_files:
        print(f"  Loading Wiser from {f.name}...")
        df_raw = pd.read_excel(f) if f.suffix == ".xlsx" else pd.read_csv(f)
        dfs.append(_map_wiser(df_raw))
    return pd.concat(dfs, ignore_index=True)


def _map_wiser(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Map Wiser column names to canonical model.
    TODO: refine once Wiser API docs / export headers are known.
    Column mapping based on Wave II Wiser Excel files.
    """
    df = pd.DataFrame()

    # Tentative mapping based on Wave II Wiser files (FAEM.xlsx, SAEM.xlsx)
    # Will need updating once actual Wave III Wiser format is confirmed
    col_map = {
        "Market":               "market",
        "Category":             "category",
        "Location ID":          "store_id",
        "Location Name":        "store_name",
        "Retailer":             "retailer",
        "Date":                 "visit_date",
        "Submission ID":        "raw_response_id",
        "KPI1_Available":       "kpi1_category_present",
        "KPI1_Brands":          "kpi1_competitor_brands",
        "KPI2_TopBrand":        "kpi2_most_standout",
        "KPI3_Recommend":       "kpi3_recommended_brand",
    }
    for raw_col, can_col in col_map.items():
        if raw_col in df_raw.columns:
            df[can_col] = df_raw[raw_col]

    df["platform"] = "wiser"
    df["wave"] = "Wave III"
    df["market_name"] = df.get("market", pd.Series()).map(MARKET_NAMES)

    for col in CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = None

    return df[CANONICAL_COLUMNS]


def extract_pinion() -> pd.DataFrame:
    """Load Pinion data (BR) from raw file or API."""
    raw_files = sorted(RAW_DIR.glob("pinion_*.xlsx")) + sorted(RAW_DIR.glob("pinion_*.csv"))

    if not raw_files:
        print("  ⚠ No Pinion raw files found in data/raw/ — returning empty frame")
        print("    Place Pinion exports as pinion_BR_*.xlsx")
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    dfs = []
    for f in raw_files:
        print(f"  Loading Pinion from {f.name}...")
        df_raw = pd.read_excel(f) if f.suffix == ".xlsx" else pd.read_csv(f)
        dfs.append(_map_pinion(df_raw))
    return pd.concat(dfs, ignore_index=True)


def _map_pinion(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Map Pinion columns to canonical model."""
    df = pd.DataFrame()
    # Based on Wave II Brasil Pinion export structure
    col_map = {
        "Categoria":        "category",
        "Loja":             "store_name",
        "Varejista":        "retailer",
        "Data":             "visit_date",
        "ID":               "raw_response_id",
        "Disponibilidade":  "kpi1_category_present",
        "Marca_Recomend":   "kpi3_recommended_brand",
    }
    for raw_col, can_col in col_map.items():
        if raw_col in df_raw.columns:
            df[can_col] = df_raw[raw_col]

    df["market"] = "BR"
    df["market_name"] = "Brazil"
    df["platform"] = "pinion"
    df["wave"] = "Wave III"

    for col in CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = None

    return df[CANONICAL_COLUMNS]


# ─── Quality checks ───────────────────────────────────────────────────────────

def run_qc(df: pd.DataFrame) -> pd.DataFrame:
    """Run quality checks and return a QC report dataframe."""
    issues = []

    # 1. Missing KPI scores
    for kpi_col in ["kpi1_category_present", "kpi2_most_standout", "kpi3_recommended_brand"]:
        if kpi_col in df.columns:
            n_missing = df[kpi_col].isna().sum()
            if n_missing > 0:
                issues.append({"check": f"Missing {kpi_col}", "count": n_missing, "severity": "warning"})

    # 2. Unknown markets
    valid_markets = {"DE", "FR", "NL", "UK", "TR", "AU", "BR", "US"}
    unknown = df[~df["market"].isin(valid_markets)]["market"].unique()
    if len(unknown) > 0:
        issues.append({"check": "Unknown market codes", "count": len(unknown), "severity": "error",
                        "detail": str(list(unknown))})

    # 3. Duplicate submissions
    if "raw_response_id" in df.columns:
        dupes = df["raw_response_id"].duplicated().sum()
        if dupes > 0:
            issues.append({"check": "Duplicate response IDs", "count": dupes, "severity": "error"})

    # 4. Brand name consistency check
    if "kpi2_most_standout" in df.columns:
        brands = df["kpi2_most_standout"].dropna().unique()
        suspicious = [b for b in brands if not isinstance(b, str) or len(b) > 50]
        if suspicious:
            issues.append({"check": "Suspicious brand values", "count": len(suspicious),
                            "severity": "warning", "detail": str(suspicious[:5])})

    qc_df = pd.DataFrame(issues)
    return qc_df


# ─── Main ─────────────────────────────────────────────────────────────────────

def run_etl(market: str | None, output_path: Path, check_only: bool = False):
    print("\n=== Versuni MS Wave III — ETL Pipeline ===\n")
    print("Step 1: Extract")
    dfs = []

    print("  [Roamler]")
    dfs.append(extract_roamler(market))

    if not market or market in ("AU", "US"):
        print("  [Wiser]")
        dfs.append(extract_wiser())

    if not market or market == "BR":
        print("  [Pinion]")
        dfs.append(extract_pinion())

    print("\nStep 2: Merge")
    master = pd.concat(dfs, ignore_index=True)
    print(f"  Total rows: {len(master):,}")

    print("\nStep 3: Quality checks")
    qc = run_qc(master)
    if len(qc) == 0:
        print("  ✓ No issues found")
    else:
        for _, row in qc.iterrows():
            icon = "❌" if row["severity"] == "error" else "⚠"
            detail = f" ({row.get('detail', '')})" if row.get("detail") else ""
            print(f"  {icon} {row['check']}: {row['count']}{detail}")

    if check_only:
        print("\nCheck-only mode — not writing output.")
        return

    print(f"\nStep 4: Write output → {output_path}")
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        master.to_excel(writer, sheet_name="Master", index=False)
        qc.to_excel(writer, sheet_name="QC Report", index=False)

        # Per-market sheets
        for mkt in master["market"].dropna().unique():
            mkt_df = master[master["market"] == mkt]
            mkt_df.to_excel(writer, sheet_name=mkt, index=False)

    print(f"  ✓ Saved ({len(master):,} rows, {master['market'].nunique()} markets)")


def main():
    parser = argparse.ArgumentParser(description="Versuni MS Wave III ETL")
    parser.add_argument("--market", "-m", help="Filter to single market code (e.g. DE)")
    parser.add_argument("--output", "-o", default="data/processed/master_wave3.xlsx")
    parser.add_argument("--check-only", action="store_true", help="Run QC without writing output")
    args = parser.parse_args()

    output_path = ROOT / args.output
    run_etl(args.market, output_path, args.check_only)


if __name__ == "__main__":
    main()
