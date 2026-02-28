# Versuni Mystery Shopping — Wave III (2026)

Tooling for the Versuni Global Mystery Shopping Program.
8 markets · 7 categories · 3 fieldwork platforms · Fieldwork start: March 9 2026

**Team:** Martijn, Daniel, Paula + external collaborators welcome

---

## Who needs what

| Role | What you need | How |
|------|--------------|-----|
| **View dashboards** (Versuni, PMs) | Browser link | [Live dashboard →](#live-dashboard) |
| **Contribute code** (team, external devs) | Clone repo + Python | [Dev setup →](#dev-setup) |
| **Check fieldwork progress** | Browser link | [Progress tracker →](#live-dashboard) |
| **Use AI assistance** (Claude Code) | Clone repo | `CLAUDE.md` is pre-configured |

---

## Live dashboard

The dashboard and progress tracker are deployed on Streamlit Cloud — no install needed.

> **Dashboard:** *(link added after Streamlit Cloud deploy)*
> **Progress tracker:** *(link added after Streamlit Cloud deploy)*

To access password-protected apps, ask Martijn for the password.

---

## Dev setup

Works on Windows, Mac, Linux. Python 3.11+ required.

### 1. Clone
```bash
git clone https://github.com/nijhuis777/versuni-ms-wave3.git
cd versuni-ms-wave3
```

### 2. Install dependencies
```bash
# Windows
py -m pip install -r requirements.txt

# Mac/Linux
pip install -r requirements.txt
```

### 3. Set up credentials
```bash
cp .env.example .env
# Edit .env and fill in your API keys
```

Need API keys? Ask Martijn. You only need the keys for the platform(s) you're working with.

### 4. Run locally

```bash
# BI Dashboard
py -m streamlit run dashboard/app.py

# Progress Tracker
py -m streamlit run progress/tracker.py

# Pull data from all platforms → master dataset
py pipeline/etl.py

# Update questionnaire for Wave III
py questionnaires/update_questionnaire.py --category FAEM

# Test Roamler API connection
py scripts/test_roamler_api.py
```

---

## Contributing

- **Branch** off `main` for your changes: `git checkout -b your-feature`
- **No secrets in commits** — `.env` and `secrets.toml` are gitignored
- **Data files** are gitignored — share via the team shared drive instead
- Open a PR when ready — Martijn reviews

### External contributors
External collaborators (e.g. Versuni-side, agency partners) can be added to the private repo as GitHub collaborators. Ask Martijn to invite you by GitHub username or email.

---

## Streamlit Cloud deployment (for Martijn to set up once)

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Connect to `nijhuis777/versuni-ms-wave3`
3. Set main file to `dashboard/app.py`
4. Add secrets from `.streamlit/secrets.toml.example` in App Settings → Secrets
5. Optionally set a password under Advanced Settings
6. Repeat for `progress/tracker.py`

---

## Markets in scope (Wave III)

| Market | Code | Platform | Categories |
|--------|------|----------|-----------|
| Netherlands | NL | Roamler | Airfryer, FAEM |
| France | FR | Roamler | Airfryer, FAEM |
| Germany | DE | Roamler | Airfryer, FAEM |
| United Kingdom | UK | Roamler | Airfryer, FAEM |
| Turkey | TR | Roamler | FAEM, Handstick VC (W&D + Dry), Steam Iron |
| Australia | AU | Wiser | FAEM, Airfryer, All-in-One, Handheld Steamer |
| Brazil | BR | Pinion | FAEM, Airfryer |
| United States | US | Wiser | FAEM |

---

## Repo structure

| Folder | Purpose |
|--------|---------|
| `config/` | Scope, brands, KPI definitions per market × category |
| `questionnaires/` | Category JSON templates + Wave III update/export tools |
| `progress/` | Live fieldwork tracker (Streamlit + Roamler/Wiser/Pinion connectors) |
| `pipeline/` | ETL — pull from all platforms → clean master dataset |
| `dashboard/` | BI dashboard (Streamlit) |
| `data/raw/` | Drop Wiser/Pinion exports here (gitignored) |
| `scripts/` | Utilities: API tests, scope parser |
| `CLAUDE.md` | Context file for Claude Code AI assistant |
