"""
Diagnose: dump the exact 1Retailer attribute object AND address field
from a sample of cached submissions across all markets.

Run from repo root:
    py scripts/diagnose_retailer.py
Output: scripts/diagnose_retailer_output.txt
"""
import json
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent / "data" / "raw" / "submissions_cache"
OUT_FILE  = Path(__file__).parent / "diagnose_retailer_output.txt"

files = sorted(CACHE_DIR.glob("*.json"))
if not files:
    OUT_FILE.write_text("No cached files found.\n")
    raise SystemExit

lines = [f"Found {len(files)} cached files. Sampling up to 30...\n"]

seen = 0
for f in files:
    if seen >= 30:
        break
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:
        lines.append(f"  ERROR reading {f.name}: {e}\n")
        continue

    market   = data.get("_market", "??")
    category = data.get("_category", "??")

    loc = data.get("location") or data.get("Location") or {}
    address = (
        loc.get("address") or loc.get("displayAddress")
        or loc.get("Address") or loc.get("DisplayAddress") or ""
    )

    raw_attrs = loc.get("attributes") or loc.get("Attributes") or []

    # Find the 1Retailer attribute (full raw object)
    retailer_attr = None
    for a in raw_attrs:
        name_val = (
            a.get("name") or a.get("Name") or
            a.get("key")  or a.get("Key")  or ""
        )
        if "retailer" in str(name_val).lower():
            retailer_attr = a
            break

    lines.append(f"── {f.name}  [{market} / {category}] ──")
    lines.append(f"   address field   : {address!r}")
    if retailer_attr:
        lines.append(f"   retailer attr   : {retailer_attr}")
        lines.append(f"   attr keys       : {list(retailer_attr.keys())}")
        for k, v in retailer_attr.items():
            lines.append(f"     {k!r:20s} → {v!r}")
    else:
        lines.append("   retailer attr   : (not found — no attr with 'retailer' in name)")
    lines.append("")
    seen += 1

OUT_FILE.write_text("\n".join(lines), encoding="utf-8")
print(f"Done. Output written to {OUT_FILE}")
