# Versuni MS Wave III — Claude Code Context

This file is automatically loaded by Claude Code for anyone working on this repo.

## Project
Global Mystery Shopping program for Versuni (Philips home appliances).
8 markets, 7 product categories, 3 fieldwork platforms, fieldwork starts March 9 2026.

## Key facts
- Platforms: Roamler (NL/FR/DE/UK/TR), Wiser (AU/US), Pinion (BR)
- All config lives in `config/scope.yaml` and `config/brands.yaml`
- API credentials go in `.env` (never commit — gitignored)
- Python 3.13+, run with `py` on Windows

## Run the apps
```bash
py -m streamlit run dashboard/app.py      # BI dashboard
py -m streamlit run progress/tracker.py  # Fieldwork tracker
py pipeline/etl.py                        # Pull + harmonise data
py questionnaires/update_questionnaire.py --category FAEM  # Update questionnaire
```

## Repo structure
- `config/`         — scope, brands, KPI config per market × category
- `questionnaires/` — Wave II JSONs → Wave III update + export tools
- `progress/`       — live fieldwork tracker (Streamlit + API connectors)
- `pipeline/`       — ETL: pull from all platforms → master dataset
- `dashboard/`      — BI dashboard (Streamlit)
- `data/raw/`       — drop Wiser/Pinion exports here (gitignored)
- `scripts/`        — utilities (test API, parse scope Excel)

## Conventions
- All platform connectors return the same row shape: `{market, category, platform, target, completed, pct, status}`
- Canonical data model columns defined in `pipeline/etl.py → CANONICAL_COLUMNS`
- Date range for data pull controlled via `.env`: `ROAMLER_DATE_FROM` / `ROAMLER_DATE_TO`
- Set dates to 2025 for preview with Wave II data; 2026-03-09 for live Wave III

## Contact
Martijn Nijhuis (project lead) — GitHub: nijhuis777
