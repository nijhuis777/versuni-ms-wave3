"""
Questionnaire Update Tool — Versuni MS Wave III
================================================
Loads a Wave II Roamler JSON questionnaire and applies Wave III config changes:
  - Updates brand answer options per category
  - Updates question text references (year, wave labels)
  - Applies any manual patches defined in a patch file

Usage:
    python questionnaires/update_questionnaire.py --category FAEM
    python questionnaires/update_questionnaire.py --category FAEM --patch patches/FAEM_wave3.yaml
    python questionnaires/update_questionnaire.py --list-categories
"""

import json
import copy
import re
import argparse
from pathlib import Path
import yaml

ROOT = Path(__file__).parent.parent
CONFIG_DIR = ROOT / "config"
QUESTIONNAIRES_DIR = ROOT / "questionnaires"
WAVE2_SOURCE_DIR = Path(r"C:\Users\MartijnNijhuis\dev\Versuni\2026\2026-001 Versuni Mystery Shopping - Wave III\Operations")
OUTPUT_DIR = QUESTIONNAIRES_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def load_config(name: str) -> dict:
    with open(CONFIG_DIR / f"{name}.yaml") as f:
        return yaml.safe_load(f)


def load_questionnaire(json_path: Path) -> dict:
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)


def save_questionnaire(data: dict, path: Path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  Saved → {path}")


def update_year_references(questionnaire: dict, from_year: str = "2025", to_year: str = "2026") -> dict:
    """Replace year references in text fields throughout the questionnaire."""
    q = copy.deepcopy(questionnaire)
    text = json.dumps(q)
    text = text.replace(from_year, to_year)
    # Also update wave references
    text = text.replace("Wave II", "Wave III").replace("Wave 2", "Wave 3")
    return json.loads(text)


def get_brand_answer_ids(questionnaire: dict) -> dict:
    """
    Find all questions that contain brand answer options.
    Returns: {question_code: [answer_codes]}
    """
    brand_questions = {}
    questions = questionnaire.get("Questions", [])
    for q in questions:
        code = q.get("Code", "")
        answers = q.get("Answers", [])
        if answers and any(
            a.get("Text", "").strip() in [
                "Philips", "Delonghi", "Siemens", "Jura", "Smeg", "Miele",
                "Tefal", "Ninja", "Bosch", "KitchenAid", "Rowenta", "Braun"
            ]
            for a in answers
        ):
            brand_questions[code] = answers
    return brand_questions


def apply_patch(questionnaire: dict, patch_path: Path) -> dict:
    """
    Apply a YAML patch file to the questionnaire.
    Patch format:
      updates:
        - question_code: Q_KPI1_Score_Q49
          field: Text
          value: "New question text here"
      add_answers:
        - question_code: Q_KPI2_Score_Q26
          answers:
            - code: A_NEW_BRAND
              text: NewBrand
              seq: 8
    """
    if not patch_path.exists():
        print(f"  No patch file at {patch_path}, skipping.")
        return questionnaire

    with open(patch_path) as f:
        patch = yaml.safe_load(f)

    q = copy.deepcopy(questionnaire)
    questions_by_code = {qu["Code"]: qu for qu in q.get("Questions", []) if "Code" in qu}

    for update in patch.get("updates", []):
        code = update["question_code"]
        if code in questions_by_code:
            questions_by_code[code][update["field"]] = update["value"]
            print(f"    Patched {code}.{update['field']}")

    for add in patch.get("add_answers", []):
        code = add["question_code"]
        if code in questions_by_code:
            for new_answer in add["answers"]:
                questions_by_code[code].setdefault("Answers", []).append(new_answer)
                print(f"    Added answer '{new_answer['text']}' to {code}")

    return q


def summarize_changes(original: dict, updated: dict):
    """Print a brief summary of what changed."""
    orig_text = json.dumps(original)
    new_text = json.dumps(updated)

    year_changes = orig_text.count("2025") - new_text.count("2025")
    wave_changes = orig_text.count("Wave II") - new_text.count("Wave II")

    print(f"\n  Summary of changes:")
    print(f"    Year references updated (2025→2026): {year_changes}")
    print(f"    Wave references updated (Wave II→III): {wave_changes}")


def process_category(category: str, patch_file: Path | None = None):
    scope = load_config("scope")
    cat_config = scope["categories"].get(category)
    if not cat_config:
        print(f"Category '{category}' not found in scope.yaml")
        return

    wave2_json_name = cat_config.get("wave2_json")
    if not wave2_json_name:
        print(f"No Wave II JSON defined for category '{category}' in scope.yaml")
        print("  → Add it under categories.{category}.wave2_json")
        return

    source_path = WAVE2_SOURCE_DIR / wave2_json_name
    if not source_path.exists():
        print(f"Source JSON not found: {source_path}")
        return

    print(f"\nProcessing category: {category}")
    print(f"  Source: {source_path}")

    original = load_questionnaire(source_path)
    updated = update_year_references(original)

    if patch_file:
        print(f"  Applying patch: {patch_file}")
        updated = apply_patch(updated, patch_file)

    summarize_changes(original, updated)

    output_path = OUTPUT_DIR / f"Versuni_{category}_Wave3.json"
    save_questionnaire(updated, output_path)


def list_categories():
    scope = load_config("scope")
    print("\nAvailable categories:")
    for code, cat in scope["categories"].items():
        wave2 = cat.get("wave2_json") or "⚠ no Wave II JSON yet"
        print(f"  {code:20s} — {cat['label']:40s} [{wave2}]")


def main():
    parser = argparse.ArgumentParser(description="Versuni Questionnaire Update Tool")
    parser.add_argument("--category", "-c", help="Category code (e.g. FAEM)")
    parser.add_argument("--patch", "-p", help="Path to YAML patch file")
    parser.add_argument("--list-categories", action="store_true", help="List all categories")
    parser.add_argument("--all", action="store_true", help="Process all categories with a Wave II JSON")
    args = parser.parse_args()

    if args.list_categories:
        list_categories()
        return

    scope = load_config("scope")

    if args.all:
        for code, cat in scope["categories"].items():
            if cat.get("wave2_json"):
                patch = Path(args.patch) if args.patch else QUESTIONNAIRES_DIR / "patches" / f"{code}_wave3.yaml"
                process_category(code, patch)
        return

    if not args.category:
        parser.print_help()
        return

    patch = Path(args.patch) if args.patch else QUESTIONNAIRES_DIR / "patches" / f"{args.category}_wave3.yaml"
    process_category(args.category, patch)


if __name__ == "__main__":
    main()
