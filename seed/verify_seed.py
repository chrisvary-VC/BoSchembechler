#!/usr/bin/env python3
"""Validate every seed file against the render-event contract.

Prints PASS or FAIL per demo question. Run before filming:
    cd seed && python3 verify_seed.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SEED = Path(__file__).resolve().parent

# Mirrors agent/aios_data.py SEED_FILES. The brief lives in daily_brief.json.
CHECKS = [
    (
        '"JARVIS, brief me."',
        "daily_brief.json",
        [("summary", str), ("signals", list), ("sections", list)],
        lambda d: (
            all("label" in s and "value" in s for s in d["signals"])
            and all("heading" in s and "lines" in s for s in d["sections"])
            and len(d["sections"]) > 0
        ),
    ),
    (
        '"How are my subscribers trending?"',
        "metrics.json",
        [("series", dict)],
        lambda d: all(
            isinstance(v.get("points"), list)
            and len(v["points"]) >= 7
            and all({"date", "value"} <= set(p) for p in v["points"])
            for v in d["series"].values()
        ),
    ),
    (
        '"What\'s at risk in my pipeline?"',
        "pipeline.json",
        [("stages", list), ("deals", list)],
        lambda d: (
            all({"name", "count", "value"} <= set(s) for s in d["stages"])
            and all({"name", "stage", "value", "at_risk"} <= set(x) for x in d["deals"])
            and any(x["at_risk"] for x in d["deals"])
        ),
    ),
    (
        '"What was said about Northwind?"',
        "intel.json",
        [("items", list)],
        lambda d: all(
            {"when", "source", "who", "quote"} <= set(i) for i in d["items"]
        )
        and len(d["items"]) > 0,
    ),
    (
        '"What should I work on today?"',
        "actions.json",
        [("items", list)],
        lambda d: all({"rank", "title", "why"} <= set(i) for i in d["items"])
        and len(d["items"]) > 0,
    ),
]


def main() -> int:
    failures = 0
    for question, filename, fields, extra in CHECKS:
        path = SEED / filename
        problems = []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            problems.append(f"missing file {filename}")
            data = None
        except json.JSONDecodeError as exc:
            problems.append(f"bad JSON in {filename}: {exc}")
            data = None

        if data is not None:
            for key, kind in fields:
                if key not in data:
                    problems.append(f"{filename} has no {key!r}")
                elif not isinstance(data[key], kind):
                    problems.append(f"{filename}:{key} should be {kind.__name__}")
            if not problems:
                try:
                    if not extra(data):
                        problems.append(f"{filename} failed its shape check")
                except Exception as exc:
                    problems.append(f"{filename} shape check errored: {exc}")

        if problems:
            failures += 1
            print(f"FAIL  {question}")
            for p in problems:
                print(f"        {p}")
        else:
            print(f"PASS  {question}  ({filename})")

    print()
    print("All five panels ready." if not failures else f"{failures} panel(s) will break on camera.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
