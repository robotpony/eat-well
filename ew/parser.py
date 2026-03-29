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

# Normalise common Unicode fraction characters to ASCII equivalents before
# attempting to match the amount regex.
_UNICODE_FRACTIONS: dict[str, str] = {
    "½": "1/2", "⅓": "1/3", "⅔": "2/3",
    "¼": "1/4", "¾": "3/4",
    "⅛": "1/8", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8",
    "⅙": "1/6", "⅚": "5/6",
    "⅕": "1/5", "⅖": "2/5", "⅗": "3/5", "⅘": "4/5",
}

# Patterns that mark the end of the food name and the start of a note.
# Matched against the food_query after the amount/unit are extracted.
_NOTE_PATTERNS = re.compile(
    r"\s+/\s+.*$"          # " / half an avocado" — slash-separated annotation
    r"|/[^/\s][^/]*$"      # "/lime juice" — inline slash alternative (no spaces)
    r"|\s+or\s+.*$"        # " or water" — alternatives
    r"|\s*\([^)]*\)*",     # "(used 75g, …)" — parenthetical anywhere in string
    re.IGNORECASE,
)

# Estimated gram weights for common piece-count units used as a last resort
# before the 1 g fallback.  Only covers units where a typical weight is
# well-established and unlikely to vary enough to mislead the totals.
_PIECE_GRAM_ESTIMATES: dict[str, float] = {
    "clove":    6.0,    # garlic clove
    "cloves":   6.0,
    "head":    50.0,    # head of garlic (smaller than a cabbage head, etc.)
    "heads":   50.0,
    "sprig":    2.0,    # fresh herb sprig
    "sprigs":   2.0,
    "bunch":   25.0,    # small bunch of fresh herbs
    "bunches": 25.0,
    "stalk":   40.0,    # celery stalk
    "stalks":  40.0,
    "ear":    150.0,    # ear of corn
    "ears":   150.0,
    "strip":   15.0,    # bacon strip
    "strips":  15.0,
    "leaf":     1.0,    # bay leaf, kaffir lime leaf, etc.
    "leaves":   1.0,
}

# Leading preparation adjectives that describe how an ingredient is prepared
# rather than what it is.  Stripped from the start of food_query before FTS.
#
# Intentionally conservative: only unambiguous mechanical-action verbs.
# Words like "ground", "whole", "fresh", "raw", "dried" are excluded because
# they are often part of the canonical food name ("ground beef", "whole milk",
# "dried apricots") and stripping them would produce the wrong FTS query.
_PREP_ADJECTIVES: frozenset[str] = frozenset({
    "sliced", "diced", "chopped", "minced", "grated", "shredded",
    "crushed", "peeled", "pitted", "trimmed", "halved", "quartered",
})

# Parenthetical amount: "garlic powder (½ teaspoon)" or "cumin (1 tsp)"
# Group 1: food name before the parenthesis
# Group 2: amount inside  (mixed fraction, simple fraction, or decimal/integer)
# Group 3: optional unit word inside the parenthesis
_PAREN_AMOUNT_RE = re.compile(
    r"^(.+?)"                                             # food name (non-greedy)
    r"\s*\("
    r"(\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)"            # amount
    r"(?:\s+([a-zA-Z]+(?:\.[a-zA-Z]*)?))?"               # optional unit
    r"[^)]*\)",                                           # rest of parenthetical
    re.IGNORECASE,
)

# Leading alternative-amount prefix produced by dual metric/imperial notation
# like "1.36kg/3 lbs" — after the compact regex consumes "1.36kg", the rest
# starts with "/3 lbs ".  Strip: /NUMBER UNIT whitespace.
_LEADING_ALT_AMOUNT_RE = re.compile(
    r"^/\d+(?:\.\d+)?\s*(?:pounds?|lbs?|kg|mg|ml|mL|cups?|tbsp|tsp|oz|g|l|L)?\s*",
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

    # Normalise Unicode fraction characters so "½ tsp" parses as "1/2 tsp".
    for uc, ascii_frac in _UNICODE_FRACTIONS.items():
        text = text.replace(uc, ascii_frac)

    # Compact unit ("100g almonds")
    m = _COMPACT_RE.match(text)
    if m:
        food_query = _clean_food_query(m.group(3).strip())
        if not food_query:
            return None
        return ParsedIngredient(float(m.group(1)), m.group(2).lower(), food_query, raw)

    # Leading amount
    m = _AMOUNT_RE.match(text)
    if not m:
        # Parenthetical amount fallback: "garlic powder (½ teaspoon)"
        pm = _PAREN_AMOUNT_RE.match(text)
        if pm:
            food_name_raw = pm.group(1).strip()
            amount_m = _AMOUNT_RE.match(pm.group(2))
            if amount_m:
                p_amount = _parse_matched_amount(amount_m)
                unit_raw = (pm.group(3) or "").lower().rstrip(".")
                p_unit: Optional[str] = unit_raw if (unit_raw in _DIRECT_G or unit_raw in _PORTION_UNITS) else None
                food_query = _clean_food_query(food_name_raw)
                if food_query:
                    return ParsedIngredient(p_amount, p_unit, food_query, raw)
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

    food_query = _clean_food_query(food_query.strip())
    if not food_query:
        return None

    return ParsedIngredient(amount, unit, food_query, raw)


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

    # Built-in estimate for common piece-count units
    for key in (unit_key, unit_key.rstrip("s")):
        if key in _PIECE_GRAM_ESTIMATES:
            est = _PIECE_GRAM_ESTIMATES[key]
            return amount * est, f"no portion in DB for '{unit}', estimated {est:g} g each"

    return amount * 1.0, f"no portion found for '{unit}', used 1 g"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _clean_food_query(text: str) -> str:
    """Strip noise from a food query so FTS finds clean ingredient names.

    Handles (in order):
        "/3 lbs "           — leading alt-amount from "1.36kg/3 lbs of ground beef"
        "of "               — leading "of" preposition ("cups of sliced mushrooms")
        "(note)"            — parenthetical anywhere ("ground beef (or veal)")
        " / annotation"     — slash-separated aside (with spaces)
        "/alternative"      — inline slash alternative ("lemon/lime juice")
        " or alternative"   — listed alternative ("stock or water")
        ", descriptor"      — preparation note after comma ("onion, diced")
        leading prep words  — "sliced mushrooms" → "mushrooms"
    """
    # 1. Strip leading alternative amount (/3 lbs, /200g …)
    text = _LEADING_ALT_AMOUNT_RE.sub("", text)
    # 2. Strip leading "of " preposition
    if text.lower().startswith("of "):
        text = text[3:]
    # 3. Strip parentheticals and slash/or notes (including inline /alternative)
    text = _NOTE_PATTERNS.sub("", text)
    # 4. Strip preparation note after first comma
    if "," in text:
        text = text[: text.index(",")]
    # 5. Strip leading preparation adjectives one at a time
    while True:
        first, _, remainder = text.partition(" ")
        if first.lower() in _PREP_ADJECTIVES and remainder:
            text = remainder
        else:
            break
    return text.strip()


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
