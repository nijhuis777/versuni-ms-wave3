# Versuni Mystery Shopping — Wave III (2026)

Internal tooling for the Versuni Global Mystery Shopping Program.

**Team:** Martijn, Daniel, Paula

## What's in this repo

| Folder | Purpose |
|--------|---------|
| `questionnaires/` | Category JSON templates + update tool |
| `progress/` | Fieldwork progress tracker (Roamler + Wiser + Pinion) |
| `pipeline/` | Data ETL — harmonize all platforms into one master dataset |
| `dashboard/` | Streamlit dashboard (web) |
| `powerbi/` | Power BI .pbix file + data connector for Versuni |
| `config/` | Market × category scope, brand lists, SKU lists |
| `data/` | Raw exports + processed master data (gitignored for large files) |

## Setup

### 1. Clone the repo
```bash
git clone https://github.com/YOUR_USERNAME/versuni-ms-wave3.git
cd versuni-ms-wave3
```

### 2. Create a virtual environment
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set up credentials
```bash
cp .env.example .env
# Fill in your API keys in .env
```

## Quick start per module

### Questionnaires
```bash
# Update a category questionnaire for Wave III
python questionnaires/update_questionnaire.py --category FAEM --config config/FAEM.yaml

# Preview changes vs Wave II
python questionnaires/diff_questionnaire.py --category FAEM
```

### Progress Tracker
```bash
streamlit run progress/tracker.py
```

### Data Pipeline
```bash
# Pull latest data from all platforms and merge
python pipeline/run_etl.py --output data/processed/master_wave3.xlsx
```

### Dashboard
```bash
streamlit run dashboard/app.py
```

## Markets in scope (Wave III)

| Market | Code | Platform |
|--------|------|----------|
| Germany | DE | Roamler |
| France | FR | Roamler |
| Netherlands | NL | Roamler |
| United Kingdom | UK | Roamler |
| Turkey | TR | Roamler |
| Australia | AU | Wiser |
| Brazil | BR | Pinion |
| United States | US | Wiser |
