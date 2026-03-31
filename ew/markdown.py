"""Markdown output renderers for `ew lookup --format md` and `ew recipe eval --format md`."""

from __future__ import annotations

import sqlite3
from typing import Optional

from .lookup import SECTIONS, fmt_value
from .recipe import MatchResult, SkipResult


def render_label_md(
    food: sqlite3.Row,
    nutrients: list[sqlite3.Row],
    portions: list[sqlite3.Row],
    per_grams: Optional[float] = None,
    lang: str = "en",
) -> str:
    """Return a markdown nutrition label.

    Mirrors the two-column layout of render_label() but as a GFM table.
    The second column is *per_grams* when supplied, otherwise the first portion.
    """
    # Resolve second column
    if per_grams is not None:
        col2_grams: Optional[float] = per_grams
        col2_label = f"per {per_grams:g} g"
    elif portions:
        first = portions[0]
        col2_grams = first["gram_weight"]
        measure = (
            first["measure_fr"]
            if lang == "fr" and first["measure_fr"]
            else first["measure_en"]
        )
        col2_label = f"{measure} ({col2_grams:g} g)"
    else:
        col2_grams = None
        col2_label = None

    display_name = (
        food["name_fr"] if lang == "fr" and food["name_fr"] else food["name_en"]
    )
    has_col2 = col2_label is not None

    lines: list[str] = [f"## {display_name} — {food['source_name']}", ""]

    if has_col2:
        lines.append(f"| Nutrient | per 100 g | {col2_label} |")
        lines.append("| --- | ---: | ---: |")
    else:
        lines.append("| Nutrient | per 100 g |")
        lines.append("| --- | ---: |")

    buckets: dict[str, list] = {name: [] for name, *_ in SECTIONS}
    buckets["Other"] = []
    for row in nutrients:
        rank = row["rank"]
        placed = False
        for sname, lo, hi in SECTIONS:
            if lo <= rank <= hi:
                buckets[sname].append(row)
                placed = True
                break
        if not placed:
            buckets["Other"].append(row)

    for sname, *_ in SECTIONS:
        rows = buckets[sname]
        if not rows:
            continue
        lines.append(f"| **{sname}** | | |" if has_col2 else f"| **{sname}** | |")
        for n in rows:
            name = n["name_fr"] if lang == "fr" and n["name_fr"] else n["name_en"]
            val_100 = fmt_value(n["value"], n["unit"])
            if has_col2:
                val_2 = fmt_value(n["value"] * col2_grams / 100.0, n["unit"]) if col2_grams else ""
                lines.append(f"| &nbsp;&nbsp;{name} | {val_100} | {val_2} |")
            else:
                lines.append(f"| &nbsp;&nbsp;{name} | {val_100} |")

    if buckets["Other"]:
        lines.append(f"| **Other** | | |" if has_col2 else "| **Other** | |")
        for n in buckets["Other"]:
            name = n["name_fr"] if lang == "fr" and n["name_fr"] else n["name_en"]
            val_100 = fmt_value(n["value"], n["unit"])
            if has_col2:
                val_2 = fmt_value(n["value"] * col2_grams / 100.0, n["unit"]) if col2_grams else ""
                lines.append(f"| &nbsp;&nbsp;{name} | {val_100} | {val_2} |")
            else:
                lines.append(f"| &nbsp;&nbsp;{name} | {val_100} |")

    lines.append("")
    return "\n".join(lines)


def render_recipe_md(
    results: list,
    totals: list[dict],
    portion_label: str = "Per 150 g",
    portion_factor: float = 0.0,
) -> str:
    """Return a markdown recipe evaluation string.

    *results* is a list of MatchResult / SkipResult objects.
    *totals* is the output of aggregate() — already summed nutrient rows.
    *portion_label* is the header for the per-portion column (e.g. "Per 150 g").
    *portion_factor* is portion_grams / total_recipe_grams; multiply total
    nutrient values by this to get the per-portion value.
    """
    lines: list[str] = []

    # Ingredient table
    lines.append("| | Ingredient | Match | Grams | Note |")
    lines.append("| --- | --- | --- | ---: | --- |")

    for r in results:
        if isinstance(r, MatchResult):
            icon = "✓" if not r.unit_warning else "⚠"
            note = r.unit_warning or ""
            lines.append(f"| {icon} | {r.raw} | {r.food_name} | {r.grams:g} g | {note} |")
        else:
            lines.append(f"| ✗ | {r.raw} | *{r.reason}* | | |")

    lines.append("")

    # Totals section
    matched = [r for r in results if isinstance(r, MatchResult)]
    n_total = len(results)
    n_matched = len(matched)
    suffix = "s" if n_total != 1 else ""
    count_label = f"{n_matched} of {n_total} ingredient{suffix} matched"
    total_grams = sum(r.grams for r in matched)
    total_col_label = f"Total ({total_grams:,.0f} g)"

    lines.append(f"### Totals — {count_label}")
    lines.append("")
    lines.append(f"| Nutrient | {total_col_label} | {portion_label} |")
    lines.append("| --- | ---: | ---: |")

    buckets: dict[str, list] = {name: [] for name, *_ in SECTIONS}
    buckets["Other"] = []
    for row in totals:
        rank = row["rank"]
        placed = False
        for sname, lo, hi in SECTIONS:
            if lo <= rank <= hi:
                buckets[sname].append(row)
                placed = True
                break
        if not placed:
            buckets["Other"].append(row)

    for sname, *_ in SECTIONS:
        rows = buckets[sname]
        if not rows:
            continue
        lines.append(f"| **{sname}** | | |")
        for n in rows:
            val = fmt_value(n["value"], n["unit"])
            per_portion = fmt_value(n["value"] * portion_factor, n["unit"])
            lines.append(f"| &nbsp;&nbsp;{n['name_en']} | {val} | {per_portion} |")

    if buckets["Other"]:
        lines.append("| **Other** | | |")
        for n in buckets["Other"]:
            val = fmt_value(n["value"], n["unit"])
            per_portion = fmt_value(n["value"] * portion_factor, n["unit"])
            lines.append(f"| &nbsp;&nbsp;{n['name_en']} | {val} | {per_portion} |")

    lines.append("")
    return "\n".join(lines)
