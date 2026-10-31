"""Render docs/qa/speed/<label>.json as a markdown table; with two labels, side by side.
    python docs/qa/speed/report.py before            → table
    python docs/qa/speed/report.py before after      → before | after | change
Times are medians in seconds, Greek format; ✗ marks a tap over its budget (1,5 s; the cold
guide result 2 s; the cold page load has no budget)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

DIR = Path(__file__).parent
BUDGET = {"cold-load": None, "cold-result-a": 2000, "cold-result-b": 2000}


def s(ms: int | None) -> str:
    return "—" if ms is None else f"{ms / 1000:.2f}".replace(".", ",") + " s"


def mark(key: str, ms: int | None) -> str:
    limit = BUDGET.get(key, 1500)
    return "" if limit is None or ms is None else (" ✓" if ms <= limit else " ✗")


def main(labels: list[str]) -> None:
    data = [json.loads((DIR / f"{x}.json").read_text()) for x in labels]
    keys = list(data[0])
    keys = [k for k in keys if k.startswith("cold")] + [k for k in keys if not k.startswith("cold")]
    cols = ["Tap", *labels, *(["αλλαγή"] if len(data) == 2 else []), "samples (ms)"]
    head = "| " + " | ".join(cols) + " |"
    print(head)
    print("|" + "---|" * (head.count("|") - 1))
    for k in keys:
        row = [d.get(k, {}) for d in data]
        cells = [s(r.get("median")) + mark(k, r.get("median")) for r in row]
        if len(data) == 2 and row[0].get("median") and row[1].get("median"):
            cells.append(f"{(row[1]['median'] / row[0]['median'] - 1) * 100:+.0f} %")
        elif len(data) == 2:
            cells.append("")
        samples = " / ".join(",".join(map(str, r.get("samples", []))) for r in row)
        print(f"| {row[0].get('name') or row[-1].get('name', k)} | " + " | ".join(cells) + f" | {samples} |")


main(sys.argv[1:] or ["before"])
