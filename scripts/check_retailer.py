"""
Diagnostic: inspect the location object of cached Roamler submissions
to find the correct attribute key for retailer name.

Run from repo root:
    py scripts/check_retailer.py
"""
import json
import sys
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent / "data" / "raw" / "submissions_cache"

files = sorted(CACHE_DIR.glob("*.json"))
if not files:
    print("No cached submission files found.")
    sys.exit(1)

print(f"Found {len(files)} cached files. Inspecting first 5...\n")

for f in files[:5]:
    print(f"── {f.name} ──")
    with open(f, encoding="utf-8") as fh:
        data = json.load(fh)

    loc = data.get("location") or data.get("Location") or {}
    print(f"  location keys: {list(loc.keys())}")

    attrs = loc.get("attributes") or loc.get("Attributes") or []
    if attrs:
        print(f"  attributes ({len(attrs)} items):")
        for a in attrs:
            name  = a.get("name")  or a.get("Name")  or a.get("key")  or a.get("Key")  or "(no name)"
            value = a.get("value") or a.get("Value") or a.get("val")  or a.get("Val")  or "(no value)"
            print(f"    {name!r:40s} → {str(value)[:60]!r}")
    else:
        print("  attributes: (empty or missing)")

    # Show direct location fields that might be retailer-like
    for key in ("retailer", "Retailer", "name", "Name", "storeName",
                "StoreName", "store_name", "address", "displayAddress"):
        val = loc.get(key)
        if val:
            print(f"  loc[{key!r}] = {str(val)[:80]!r}")

    print()
