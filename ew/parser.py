"""Ingredient string parsing and unit-to-gram resolution."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedIngredient:
    amount: float
    unit: Optional[str]   # None when no unit word was found
    food_query: str       # the ingredient name to search for
    raw: str              # original input text


# ---------------------------------------------------------------------------
# Unit tables
# ---------------------------------------------------------------------------

# Units with a fixed conversion to grams.
_DIRECT_G: dict[str, float] = {
    "g": 1.0,
    "gram": 1.0,
    "grams": 1.0,
    "kg": 1000.0,
    "kilogram": 1000.0,
    "kilograms": 1000.0,
    "mg": 0.001,
    "oz": 28.3495,
    "ounce": 28.3495,
    "ounces": 28.3495,
    "lb": 453.592,
    "lbs": 453.592,
    "pound": 453.592,
    "pounds": 453.592,
    "ml": 1.0,   # water approximation; good enough for most liquid ingredients
    "mL": 1.0,
    "l": 1000.0,
    "L": 1000.0,
    "liter": 1000.0,
    "litre": 1000.0,
    "liters": 1000.0,
    "litres": 1000.0,
}

# Units that need a food_portion table lookup.
_PORTION_UNITS: frozenset[str] = frozenset({
    "cup", "cups", "c",
    "tbsp", "tablespoon", "tablespoons",
    "tsp", "teaspoon", "teaspoons",
    "piece", "pieces",
    "slice", "slices",
    "clove", "cloves",
    "can", "cans",
    "large", "medium", "small",
    "serving", "servings",
    "bar", "bars",
    "packet", "packets",
    "sprig", "sprigs",
    "head", "heads",
    "bunch", "bunches",
})

# Canonical search strings for fuzzy portion matching.
_UNIT_ALIASES: dict[str, list[str]] = {
    "cup":          ["cup"],
    "cups":         ["cup"],
    "c":            ["cup"],
    "tbsp":         ["tbsp", "tablespoon"],
    "tablespoon":   ["tbsp", "tablespoon"],
    "tablespoons":  ["tbsp", "tablespoon"],
    "tsp":          ["tsp", "teaspoon"],
    "teaspoon":     ["tsp", "teaspoon"],
    "teaspoons":    ["tsp", "teaspoon"],
    "large":        ["large"],
    "medium":       ["medium"],
    "small":        ["small"],
    "slice":        ["slice"],
    "slices":       ["slice"],
    "piece":        ["piece", "each"],
    "pieces":       ["piece", "each"],
    "clove":        ["clove"],
    "cloves":       ["clove"],
    "serving":      ["serving"],
    "servings":     ["serving"],
    "bar":          ["bar"],
    "bars":         ["bar"],
    "can":          ["can"],
    "cans":         ["can"],
}

# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------

# Leading amount: mixed fraction ("1 1/2"), simple fraction ("1/2"), or number ("1", "1.5").
# Groups: (1,2,3) mixed  |  (4,5) simple fraction  |  (6) number/decimal
_AMOUNT_RE = re.compile(
    r"^(\d+)\s+(\d+)/(\d+)"    # mixed fraction
    r"|^(\d+)/(\d+)"            # simple fraction
    r"|^(\d+(?:\.\d+)?)"        # integer or decimal
)

# Compact unit glued to a number with no space: "100g", "250ml", "1.5kg"
_COMPACT_RE = re.compile(
    r"^(\d+(?:\.\d+)?)(g|kg|mg|ml|mL|l|L)\b\s*(.*)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_ingredient(text: str) -> Optional[ParsedIngredient]:
    """Parse one ingredient line into amount, unit, and food search query.

    Returns None for blank lines, comment lines (#…), and lines with no
    leading number.

    Handles:
        "1 cup whole milk"    → (1.0, "cup",   "whole milk")
        "1/2 cup olive oil"   → (0.5, "cup",   "olive oil")
        "1 1/2 cups flour"    → (1.5, "cups",  "flour")
        "100g almonds"        → (100, "g",      "almonds")
        "2 large eggs"        → (2.0, "large",  "eggs")
        "3 cloves garlic"     → (3.0, "cloves", "garlic")
        "salt to taste"       → None
        "# comment"           → None
    """
    raw = text
    text = text.strip()

    if not text or text.startswith("#"):
        return None

    # Compact unit ("100g almonds")
    m = _COMPACT_RE.match(text)
    if m:
        food_query = m.group(3).strip()
        if not food_query:
            return None
        return ParsedIngredient(float(m.group(1)), m.group(2).lower(), food_query, raw)

    # Leading amount
    m = _AMOUNT_RE.match(text)
    if not m:
        return None

    amount = _parse_matched_amount(m)
    rest = text[m.end():].strip()

    if not rest:
        return None

    # First word might be a unit
    words = rest.split(None, 1)
    first = words[0].lower().rstrip(".")
    if first in _DIRECT_G or first in _PORTION_UNITS:
        unit: Optional[str] = first
        food_query = words[1].strip() if len(words) > 1 else ""
    else:
        unit = None
        food_query = rest

    if not food_query.strip():
        return None

    return ParsedIngredient(amount, unit, food_query.strip(), raw)


def resolve_grams(
    amount: float,
    unit: Optional[str],
    portions: list,
) -> tuple[float, Optional[str]]:
    """Convert an amount + unit into grams.

    Uses direct conversion tables first, then looks up the food_portion
    table, then falls back to 1 g per unit with a warning.

    Returns (grams, warning_or_None).
    """
    if unit is None:
        piece = _find_piece_portion(portions)
        if piece:
            return amount * piece["gram_weight"], None
        return amount * 1.0, "no unit given, used 1 g per item"

    unit_key = unit.lower()

    # Direct conversion (try exact key then de-pluralised form)
    for key in (unit_key, unit_key.rstrip("s")):
        if key in _DIRECT_G:
            return amount * _DIRECT_G[key], None

    # Portion table lookup
    best = _best_portion_match(unit_key, portions)
    if best:
        return amount * best["gram_weight"], None

    return amount * 1.0, f"no portion found for '{unit}', used 1 g"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _parse_matched_amount(m: re.Match) -> float:
    if m.group(1) is not None:                               # mixed fraction
        return float(m.group(1)) + float(m.group(2)) / float(m.group(3))
    if m.group(4) is not None:                               # simple fraction
        return float(m.group(4)) / float(m.group(5))
    return float(m.group(6))                                 # integer or decimal


def _find_piece_portion(portions: list):
    """Return the first portion that looks like a single item, or None."""
    keywords = ("piece", "each", "item", "unit", "medium", "large", "small")
    for p in portions:
        if any(kw in p["measure_en"].lower() for kw in keywords):
            return p
    return None


def _best_portion_match(unit: str, portions: list):
    """Return the first portion whose measure_en contains a matching alias."""
    if not portions:
        return None
    targets = _UNIT_ALIASES.get(unit, [unit])
    for portion in portions:
        measure = portion["measure_en"].lower()
        for target in targets:
            if target in measure:
                return portion
    return None
