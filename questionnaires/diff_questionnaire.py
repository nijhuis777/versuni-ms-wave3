"""
Questionnaire Diff Tool — Versuni MS Wave III
=============================================
Compares a Wave II questionnaire against a Wave III output to show exactly what changed.
Useful for team review before uploading to platforms.

Usage:
    python questionnaires/diff_questionnaire.py --category FAEM
    python questionnaires/diff_questionnaire.py --category FAEM --format html
"""

import json
import argparse
from pathlib import Path
from deepdiff import DeepDiff
import yaml

ROOT = Path(__file__).parent.parent
CONFIG_DIR = ROOT / "config"
WAVE2_SOURCE_DIR = Path(r"C:\Users\MartijnNijhuis\dev\Versuni\2026\2026-001 Versuni Mystery Shopping - Wave III\Operations")
OUTPUT_DIR = ROOT / "questionnaires" / "output"


def load_config(name: str) -> dict:
    with open(CONFIG_DIR / f"{name}.yaml") as f:
        return yaml.safe_load(f)


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def diff_category(category: str, output_format: str = "text"):
    scope = load_config("scope")
    cat_config = scope["categories"].get(category)

    if not cat_config or not cat_config.get("wave2_json"):
        print(f"No Wave II source for category '{category}'")
        return

    wave2_path = WAVE2_SOURCE_DIR / cat_config["wave2_json"]
    wave3_path = OUTPUT_DIR / f"Versuni_{category}_Wave3.json"

    if not wave2_path.exists():
        print(f"Wave II source not found: {wave2_path}")
        return
    if not wave3_path.exists():
        print(f"Wave III output not found: {wave3_path}")
        print("  Run update_questionnaire.py first.")
        return

    wave2 = load_json(wave2_path)
    wave3 = load_json(wave3_path)

    diff = DeepDiff(wave2, wave3, ignore_order=True, verbose_level=2)

    print(f"\n=== DIFF: {category} (Wave II → Wave III) ===\n")

    if not diff:
        print("  No differences found.")
        return

    changes = diff.get("values_changed", {})
    print(f"  Changed values: {len(changes)}")
    for key, change in list(changes.items())[:50]:
        print(f"    {key}")
        print(f"      WAS: {change['old_value']}")
        print(f"      NOW: {change['new_value']}")

    added = diff.get("dictionary_item_added", set())
    removed = diff.get("dictionary_item_removed", set())
    if added:
        print(f"\n  Added fields ({len(added)}):")
        for item in list(added)[:20]:
            print(f"    + {item}")
    if removed:
        print(f"\n  Removed fields ({len(removed)}):")
        for item in list(removed)[:20]:
            print(f"    - {item}")


def main():
    parser = argparse.ArgumentParser(description="Diff Wave II vs Wave III questionnaires")
    parser.add_argument("--category", "-c", required=True)
    parser.add_argument("--format", default="text", choices=["text", "html"])
    args = parser.parse_args()
    diff_category(args.category, args.format)


if __name__ == "__main__":
    main()
