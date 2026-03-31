"""HTML output renderers for `ew lookup --format html` and `ew recipe eval --format html`."""

from __future__ import annotations

import html as _html
import sqlite3
from typing import Optional

from .lookup import SECTIONS, fmt_value
from .recipe import MatchResult, SkipResult

# ---------------------------------------------------------------------------
# Shared CSS — mirrors the minimal, system-font style from the design reference
# ---------------------------------------------------------------------------

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 "Helvetica Neue", Arial, sans-serif;
    font-size: 14px;
    line-height: 1.5;
    color: #1a1a1a;
    background: #fff;
    max-width: 700px;
    margin: 2rem auto;
    padding: 0 1.25rem 3rem;
}
h1 { font-size: 1.1rem; font-weight: 600; margin-bottom: 0.2rem; }
h2 { font-size: 1rem; font-weight: 700; margin: 1.75rem 0 0.75rem; }
.source { color: #888; font-size: 12px; margin-bottom: 1.25rem; }
table { width: 100%; border-collapse: collapse; margin-bottom: 0.5rem; }
th {
    text-align: left;
    font-size: 12px;
    font-weight: 600;
    color: #555;
    border-bottom: 1px solid #ddd;
    padding: 5px 6px 5px 0;
}
th.r, td.r { text-align: right; }
td { padding: 4px 6px 4px 0; vertical-align: top; }
.icon { width: 18px; }
.ok   { color: #2a7a2a; }
.warn { color: #a06000; }
.skip { color: #cc2222; }
.dim  { color: #888; font-style: italic; }
.note { color: #888; font-size: 12px; }
.sec  { font-weight: 700; padding-top: 0.9rem; }
.sec td { padding-top: 0.9rem; }
.ind td:first-child { padding-left: 1rem; }
"""


def _e(text: str) -> str:
    """HTML-escape a string."""
    return _html.escape(str(text))


def _doc(title: str, body: str) -> str:
    """Wrap a body fragment in a complete HTML document."""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{_e(title)}</title>\n"
        f"<style>{_CSS}</style>\n"
        "</head>\n"
        f"<body>\n{body}\n</body>\n"
        "</html>\n"
    )


# ---------------------------------------------------------------------------
# Shared nutrient table builder
# ---------------------------------------------------------------------------

def _nutrient_table(
    nutrients: list,
    col2_label: Optional[str],
    col2_grams: Optional[float],
    lang: str,
) -> str:
    has_col2 = col2_label is not None
    col2_th = f'<th class="r">{_e(col2_label)}</th>' if has_col2 else ""

    rows: list[str] = [
        "<table>",
        f'<thead><tr><th>Nutrient</th><th class="r">per 100 g</th>{col2_th}</tr></thead>',
        "<tbody>",
    ]

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
        section_rows = buckets[sname]
        if not section_rows:
            continue
        colspan = 3 if has_col2 else 2
        rows.append(f'<tr class="sec"><td colspan="{colspan}"><strong>{_e(sname)}</strong></td></tr>')
        for n in section_rows:
            name = n["name_fr"] if lang == "fr" and n["name_fr"] else n["name_en"]
            val_100 = fmt_value(n["value"], n["unit"])
            col2_td = ""
            if has_col2:
                val_2 = fmt_value(n["value"] * col2_grams / 100.0, n["unit"]) if col2_grams else ""
                col2_td = f'<td class="r">{_e(val_2)}</td>'
            rows.append(
                f'<tr class="ind"><td>{_e(name)}</td>'
                f'<td class="r">{_e(val_100)}</td>{col2_td}</tr>'
            )

    if buckets["Other"]:
        colspan = 3 if has_col2 else 2
        rows.append(f'<tr class="sec"><td colspan="{colspan}"><strong>Other</strong></td></tr>')
        for n in buckets["Other"]:
            name = n["name_fr"] if lang == "fr" and n["name_fr"] else n["name_en"]
            val_100 = fmt_value(n["value"], n["unit"])
            col2_td = ""
            if has_col2:
                val_2 = fmt_value(n["value"] * col2_grams / 100.0, n["unit"]) if col2_grams else ""
                col2_td = f'<td class="r">{_e(val_2)}</td>'
            rows.append(
                f'<tr class="ind"><td>{_e(name)}</td>'
                f'<td class="r">{_e(val_100)}</td>{col2_td}</tr>'
            )

    rows.extend(["</tbody>", "</table>"])
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_label_html(
    food: sqlite3.Row,
    nutrients: list[sqlite3.Row],
    portions: list[sqlite3.Row],
    per_grams: Optional[float] = None,
    lang: str = "en",
) -> str:
    """Return a complete HTML document for a nutrition label."""
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

    body = (
        f"<h1>{_e(display_name)}</h1>\n"
        f'<p class="source">{_e(food["source_name"])}</p>\n'
        + _nutrient_table(nutrients, col2_label, col2_grams, lang)
    )
    return _doc(display_name, body)


def render_recipe_html(
    results: list,
    totals: list[dict],
    portion_label: str = "Per 150 g",
    portion_factor: float = 0.0,
) -> str:
    """Return a complete HTML document for a recipe evaluation.

    *portion_label* is the header for the per-portion column.
    *portion_factor* is portion_grams / total_recipe_grams; multiply total
    nutrient values by this to get the per-portion value.
    """

    # Ingredient table
    ing_rows: list[str] = [
        "<table>",
        "<thead><tr>"
        '<th class="icon"></th>'
        "<th>Ingredient</th>"
        "<th>Match</th>"
        '<th class="r">Grams</th>'
        "<th>Note</th>"
        "</tr></thead>",
        "<tbody>",
    ]

    for r in results:
        if isinstance(r, MatchResult):
            if r.unit_warning:
                icon = '<span class="warn">&#9651;</span>'  # △
            else:
                icon = '<span class="ok">&#10003;</span>'   # ✓
            note = f'<span class="note">{_e(r.unit_warning)}</span>' if r.unit_warning else ""
            ing_rows.append(
                f"<tr>"
                f'<td class="icon">{icon}</td>'
                f"<td>{_e(r.raw)}</td>"
                f"<td>{_e(r.food_name)}</td>"
                f'<td class="r">{r.grams:g} g</td>'
                f"<td>{note}</td>"
                f"</tr>"
            )
        else:
            ing_rows.append(
                f"<tr>"
                f'<td class="icon"><span class="skip">&#10007;</span></td>'
                f"<td>{_e(r.raw)}</td>"
                f'<td class="dim">{_e(r.reason)}</td>'
                f'<td class="r"></td>'
                f"<td></td>"
                f"</tr>"
            )

    ing_rows.extend(["</tbody>", "</table>"])
    ing_html = "\n".join(ing_rows)

    # Totals heading
    matched = [r for r in results if isinstance(r, MatchResult)]
    n_total = len(results)
    n_matched = len(matched)
    suffix = "s" if n_total != 1 else ""
    count_label = f"Totals \u2014 {n_matched} of {n_total} ingredient{suffix} matched"
    total_grams = sum(r.grams for r in matched)
    total_col_label = f"Total ({total_grams:,.0f} g)"

    # Totals nutrient table — always two data columns: Total + per-portion
    tot_rows: list[str] = ["<table>"]
    tot_rows.append(
        f'<thead><tr><th>Nutrient</th><th class="r">{_e(total_col_label)}</th>'
        f'<th class="r">{_e(portion_label)}</th></tr></thead>'
    )
    tot_rows.append("<tbody>")

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
        section_rows = buckets[sname]
        if not section_rows:
            continue
        tot_rows.append(
            f'<tr class="sec"><td colspan="3"><strong>{_e(sname)}</strong></td></tr>'
        )
        for n in section_rows:
            val = fmt_value(n["value"], n["unit"])
            per_portion = fmt_value(n["value"] * portion_factor, n["unit"])
            tot_rows.append(
                f'<tr class="ind"><td>{_e(n["name_en"])}</td>'
                f'<td class="r">{_e(val)}</td>'
                f'<td class="r">{_e(per_portion)}</td></tr>'
            )

    if buckets["Other"]:
        tot_rows.append(
            '<tr class="sec"><td colspan="3"><strong>Other</strong></td></tr>'
        )
        for n in buckets["Other"]:
            val = fmt_value(n["value"], n["unit"])
            per_portion = fmt_value(n["value"] * portion_factor, n["unit"])
            tot_rows.append(
                f'<tr class="ind"><td>{_e(n["name_en"])}</td>'
                f'<td class="r">{_e(val)}</td>'
                f'<td class="r">{_e(per_portion)}</td></tr>'
            )

    tot_rows.extend(["</tbody>", "</table>"])
    tot_html = "\n".join(tot_rows)

    body = f"{ing_html}\n<h2>{_e(count_label)}</h2>\n{tot_html}"
    return _doc("Recipe", body)
