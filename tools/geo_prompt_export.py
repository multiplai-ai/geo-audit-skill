#!/usr/bin/env python3
"""
Validate a GEO prompt-set CSV against the /cmo/geo/share-of-answers schema.

Checks:
  * required columns present (prompt_id, prompt_text, intent_type, topic, priority)
  * intent_type values are in the locked vocabulary
  * priority values are in the allowed enum
  * prompt_id values are unique and prompt_text is non-empty
  * all 5 intent classes have >= 1 prompt
  * shopping class meets the floor (default 40%)
  * no non-shopping class exceeds the soft 50% cap (warning only)

Usage:
    python3 tools/geo_prompt_export.py <csv_path>
    python3 tools/geo_prompt_export.py <csv_path> --strict
    python3 tools/geo_prompt_export.py <csv_path> --shopping-floor 50

Exit codes:
    0  valid (warnings allowed unless --strict)
    1  invalid (missing cols, bad enum, duplicates, below floor, missing classes)
    2  file / arg error
"""
import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

# Locked vocabulary — must match 01_share-of-answers.md and 02_prompt-set-builder.md.
INTENT_CLASSES = {"shopping", "comparative", "informational", "decision", "recommendation"}
PRIORITY_LEVELS = {"high", "medium", "low"}

REQUIRED_COLS = ["prompt_id", "prompt_text", "intent_type", "topic", "priority"]
OPTIONAL_COLS = ["expected_product_visibility", "notes"]

DEFAULT_SHOPPING_FLOOR_PCT = 40
CLASS_CAP_WARN_PCT = 50


def load_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def validate(rows: list[dict], shopping_floor: int) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not rows:
        errors.append("CSV has no data rows")
        return errors, warnings

    cols = set(rows[0].keys())
    missing = [c for c in REQUIRED_COLS if c not in cols]
    if missing:
        errors.append(f"Missing required columns: {missing}")
        return errors, warnings  # downstream checks unsafe without required cols

    bad_intents = {r["intent_type"] for r in rows} - INTENT_CLASSES
    if bad_intents:
        errors.append(
            f"Invalid intent_type values: {sorted(bad_intents)}. "
            f"Locked vocab: {sorted(INTENT_CLASSES)}"
        )

    bad_priorities = {r["priority"] for r in rows} - PRIORITY_LEVELS
    if bad_priorities:
        errors.append(
            f"Invalid priority values: {sorted(bad_priorities)}. "
            f"Allowed: {sorted(PRIORITY_LEVELS)}"
        )

    ids = [r["prompt_id"] for r in rows]
    dupes = sorted({i for i, count in Counter(ids).items() if count > 1})
    if dupes:
        errors.append(f"Duplicate prompt_id values: {dupes}")

    empty_text = [r["prompt_id"] for r in rows if not r["prompt_text"].strip()]
    if empty_text:
        errors.append(f"Empty prompt_text on rows: {empty_text}")

    counts = Counter(r["intent_type"] for r in rows)
    total = len(rows)

    missing_classes = INTENT_CLASSES - set(counts.keys())
    if missing_classes:
        errors.append(
            f"Missing intent classes: {sorted(missing_classes)} "
            f"— all 5 classes must have at least one prompt"
        )

    shopping_pct = 100 * counts.get("shopping", 0) / total
    if shopping_pct < shopping_floor:
        errors.append(
            f"Shopping-intent share {shopping_pct:.1f}% below floor "
            f"{shopping_floor}% — regenerate with more shopping prompts"
        )

    for cls, n in counts.items():
        pct = 100 * n / total
        if pct > CLASS_CAP_WARN_PCT and cls != "shopping":
            warnings.append(
                f"Class '{cls}' is {pct:.1f}% of the set "
                f"(above {CLASS_CAP_WARN_PCT}% soft cap)"
            )

    return errors, warnings


def report(rows: list[dict], errors: list[str], warnings: list[str]) -> None:
    total = len(rows)
    counts = Counter(r["intent_type"] for r in rows) if rows else Counter()

    print(f"Prompt set: {total} rows\n")
    print("Distribution by intent_type:")
    for cls in sorted(INTENT_CLASSES):
        n = counts.get(cls, 0)
        pct = 100 * n / total if total else 0
        print(f"  {cls:<16} {n:>4}  ({pct:5.1f}%)")
    print()

    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print(f"  - {w}")
        print()

    if errors:
        print("ERRORS:")
        for e in errors:
            print(f"  - {e}")
        print()
        print("Status: INVALID")
    else:
        print("Status: VALID" + (" (with warnings)" if warnings else ""))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("csv_path", type=Path, help="Path to prompt-set CSV")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on warnings as well as errors",
    )
    parser.add_argument(
        "--shopping-floor",
        type=int,
        default=DEFAULT_SHOPPING_FLOOR_PCT,
        help=f"Min %% of set that must be shopping class (default: {DEFAULT_SHOPPING_FLOOR_PCT})",
    )
    opts = parser.parse_args()

    if not opts.csv_path.exists():
        print(f"ERROR: file not found: {opts.csv_path}", file=sys.stderr)
        return 2

    try:
        rows = load_csv(opts.csv_path)
    except Exception as e:
        print(f"ERROR reading {opts.csv_path}: {e}", file=sys.stderr)
        return 2

    errors, warnings = validate(rows, opts.shopping_floor)
    report(rows, errors, warnings)

    if errors:
        return 1
    if warnings and opts.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
