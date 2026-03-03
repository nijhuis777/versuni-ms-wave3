"""
KPI Scoring Engine — Versuni Mystery Shopping
==============================================
Loads the category questionnaire JSONs from the Operations folder and builds
scoring lookup tables.

Scoring logic (from PowerBI Description page):
  - Each answer option code follows the pattern  KPI{n}_Q{m}_{value}
    where {value} is the point contribution (1 = good, 0 = neutral/bad).
  - Score per KPI  = sum(earned points for KPI n) / max(possible points for KPI n) × 100
  - Total score    = sum(all earned points) / sum(all max points) × 100

Usage:
    from pipeline.scoring import ScoringEngine
    engine = ScoringEngine()
    scores = engine.score_submission(submission_answers, category="FAEM")
"""

import json
import re
from pathlib import Path
from typing import Any

# ── Paths ─────────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).parent.parent
_OPS_DIR   = _REPO_ROOT.parent / "Operations"   # ../<project>/Operations/

# Canonical category → JSON filename stem in Operations folder
CATEGORY_JSON_MAP: dict[str, str] = {
    "FAEM":              "Versuni_FAEM",
    "SAEM":              "Versuni_SAEM",
    "Airfryer":          "Versuni_Airfryer",
    "Handheld_Steamer":  "Versuni_Handheld_steamer",
    "Handstick_Dry":     "Versuni_Handsticks_Dry",
    "Handstick_WD":      "Versuni_Handsticks W&D",
    "RVC":               "Versuni_RVC",
    "Steam_Iron":        "Versuni_Steam_Iron",
    "Steam_Generator":   "Versuni_Steam_Generator",
}

# Pattern: KPI{n}_Q{m}_{value}  where value is an integer (0, 1, 2, …)
_ANSWER_CODE_RE = re.compile(r"^KPI(\d+)_Q(\d+)_(\d+)$", re.IGNORECASE)


def _parse_answer_code(code: str) -> tuple[int, int, int] | None:
    """Return (kpi_number, question_number, points) or None if not a KPI code."""
    if not code:
        return None
    m = _ANSWER_CODE_RE.match(code.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


class ScoringEngine:
    """
    Loads all category JSONs from the Operations folder and provides
    scoring rules for each category.

    Attributes built per category:
        _q_code_to_kpi[category][question_code]   = kpi_number (1, 2, or 3)
        _answer_points[category][answer_opt_code]  = points (int)
        _max_points[category][kpi_number]          = max possible points (int)
        _q_id_to_code[category][question_id]       = question_code (str)
    """

    def __init__(self, ops_dir: Path | None = None):
        self._dir = ops_dir or _OPS_DIR
        self._q_code_to_kpi:  dict[str, dict[str, int]]  = {}
        self._answer_points:  dict[str, dict[str, int]]  = {}
        self._max_points:     dict[str, dict[int, int]]  = {}
        self._q_id_to_code:   dict[str, dict[int, str]]  = {}
        self._q_text_to_code: dict[str, dict[str, str]]  = {}

        for category, stem in CATEGORY_JSON_MAP.items():
            path = self._dir / f"{stem}.json"
            if path.exists():
                self._load_category(category, path)
            else:
                print(f"  [scoring] WARNING: {path} not found — skipping {category}")

    # ── Private helpers ────────────────────────────────────────────────────────

    def _load_category(self, category: str, path: Path) -> None:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        questions = data.get("Questions") or data.get("questions") or []

        q_code_to_kpi:  dict[str, int]  = {}
        answer_points:  dict[str, int]  = {}
        max_per_kpi:    dict[int, int]  = {}
        q_id_to_code:   dict[int, str]  = {}
        q_text_to_code: dict[str, str]  = {}

        for q in questions:
            q_id   = q.get("Id") or q.get("id")
            q_code = (q.get("Code") or q.get("code") or "").strip()
            q_text = (q.get("Text") or q.get("text") or "").strip()

            # Normalise text key (first 120 chars, lowercased, spaces collapsed)
            q_text_short = " ".join(q_text.split())[:120].lower()

            if q_id and q_code:
                q_id_to_code[int(q_id)] = q_code
            if q_text_short and q_code:
                q_text_to_code[q_text_short] = q_code

            # Is this a KPI-scored question?
            answer_opts = q.get("AnswerOptions") or q.get("answerOptions") or []
            kpi_num_for_q = None
            q_max_pts = 0

            for opt in answer_opts:
                opt_code = (opt.get("Code") or opt.get("code") or "").strip()
                parsed = _parse_answer_code(opt_code)
                if parsed:
                    kpi_num, _, pts = parsed
                    answer_points[opt_code] = pts
                    if kpi_num_for_q is None:
                        kpi_num_for_q = kpi_num
                    if pts > q_max_pts:
                        q_max_pts = pts

            if kpi_num_for_q is not None and q_code:
                q_code_to_kpi[q_code] = kpi_num_for_q
                max_per_kpi[kpi_num_for_q] = (
                    max_per_kpi.get(kpi_num_for_q, 0) + q_max_pts
                )

        self._q_code_to_kpi[category]  = q_code_to_kpi
        self._answer_points[category]  = answer_points
        self._max_points[category]     = max_per_kpi
        self._q_id_to_code[category]   = q_id_to_code
        self._q_text_to_code[category] = q_text_to_code

    # ── Public API ─────────────────────────────────────────────────────────────

    def score_submission(
        self,
        answers: list[dict],
        category: str,
        questions: list[dict] | None = None,
    ) -> dict[str, float]:
        """
        Calculate KPI scores for a single submission.

        Parameters
        ----------
        answers:
            List of answer dicts from the Roamler submission detail.
            Each dict should have keys: questionId, answerOptions, text, value.
        category:
            Canonical category name (e.g. 'FAEM', 'Airfryer').
        questions:
            Optional list of question dicts from the same submission detail
            (used to resolve questionId → question Code when category JSON
            is not available or IDs have changed).

        Returns
        -------
        dict with keys:
            kpi1_score, kpi2_score, kpi3_score, total_score  (all 0–100 floats)
            kpi1_points, kpi2_points, kpi3_points
            kpi1_max, kpi2_max, kpi3_max
        """
        cat_pts  = self._answer_points.get(category, {})
        cat_max  = self._max_points.get(category, {})
        id2code  = self._q_id_to_code.get(category, {})

        # Build a quick lookup from submission's own question list (fallback)
        sub_id2code: dict[int, str] = {}
        if questions:
            for q in questions:
                qid   = q.get("id") or q.get("Id")
                qcode = q.get("code") or q.get("Code") or ""
                if qid and qcode:
                    sub_id2code[int(qid)] = qcode

        earned: dict[int, int] = {1: 0, 2: 0, 3: 0}

        for ans in answers:
            q_id = ans.get("questionId") or ans.get("QuestionId")
            if q_id is None:
                continue
            q_id = int(q_id)

            # Resolve question Code: prefer category JSON lookup, then submission's own
            q_code = id2code.get(q_id) or sub_id2code.get(q_id, "")
            if not q_code:
                continue

            # Only score KPI questions
            kpi_num = (
                self._q_code_to_kpi.get(category, {}).get(q_code)
            )
            if kpi_num is None:
                continue

            # Sum points from selected answer options
            for opt in ans.get("answerOptions") or ans.get("AnswerOptions") or []:
                opt_code = (opt.get("code") or opt.get("Code") or "").strip()
                pts = cat_pts.get(opt_code, 0)
                earned[kpi_num] += pts

        # Calculate percentages
        def pct(kpi: int) -> float:
            mx = cat_max.get(kpi, 0)
            if mx == 0:
                return 0.0
            return round(min(earned[kpi] / mx * 100, 100), 2)

        total_earned = sum(earned.values())
        total_max    = sum(cat_max.get(k, 0) for k in [1, 2, 3])

        return {
            "kpi1_score":  pct(1),
            "kpi2_score":  pct(2),
            "kpi3_score":  pct(3),
            "total_score": round(total_earned / total_max * 100, 2) if total_max else 0.0,
            "kpi1_points": earned[1],
            "kpi2_points": earned[2],
            "kpi3_points": earned[3],
            "kpi1_max":    cat_max.get(1, 0),
            "kpi2_max":    cat_max.get(2, 0),
            "kpi3_max":    cat_max.get(3, 0),
        }

    def get_max_points(self, category: str) -> dict[int, int]:
        """Return {1: max_kpi1, 2: max_kpi2, 3: max_kpi3} for a category."""
        return dict(self._max_points.get(category, {}))

    def resolve_question_code(self, category: str, question_id: int) -> str | None:
        """Resolve numeric question ID → question Code string."""
        return self._q_id_to_code.get(category, {}).get(question_id)

    def resolve_by_text(self, category: str, question_text: str) -> str | None:
        """Resolve question by text prefix (first 120 chars, lowercased)."""
        key = " ".join(question_text.split())[:120].lower()
        return self._q_text_to_code.get(category, {}).get(key)

    @property
    def categories(self) -> list[str]:
        return list(self._q_code_to_kpi.keys())


# ── Singleton ──────────────────────────────────────────────────────────────────
_engine: ScoringEngine | None = None


def get_engine() -> ScoringEngine:
    """Return a cached singleton ScoringEngine."""
    global _engine
    if _engine is None:
        _engine = ScoringEngine()
    return _engine
