"""Data structures and nutrient aggregation for recipe evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class MatchResult:
    """A successfully matched and resolved ingredient line."""
    raw: str
    food_id: int
    food_name: str
    source_name: str
    grams: float
    unit_warning: Optional[str]
    nutrients: list   # list of sqlite3.Row from get_nutrients() at resolved grams


@dataclass
class SkipResult:
    """A line that could not be parsed or matched."""
    raw: str
    reason: str


def aggregate(nutrient_rows_list: list[list]) -> list[dict]:
    """Sum nutrients across multiple matched ingredients.

    Each element of *nutrient_rows_list* is a list of sqlite3.Row objects
    returned by ``get_nutrients()`` at the ingredient's resolved gram weight.

    Returns a list of ``{"name_en", "unit", "rank", "value"}`` dicts sorted
    by rank, suitable for rendering a totals table.
    """
    totals: dict[tuple, dict] = {}
    for rows in nutrient_rows_list:
        for row in rows:
            key = (row["name_en"], row["unit"])
            if key not in totals:
                totals[key] = {
                    "name_en": row["name_en"],
                    "unit":    row["unit"],
                    "rank":    row["rank"],
                    "value":   0.0,
                }
            totals[key]["value"] += row["value"]
    return sorted(totals.values(), key=lambda x: x["rank"])
