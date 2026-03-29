"""Tests for ingredient string parsing and gram resolution."""

import pytest

from ew.parser import ParsedIngredient, parse_ingredient, resolve_grams


# ---------------------------------------------------------------------------
# parse_ingredient — basic cases
# ---------------------------------------------------------------------------

def test_integer_with_unit():
    r = parse_ingredient("1 cup whole milk")
    assert r is not None
    assert r.amount == 1.0
    assert r.unit == "cup"
    assert r.food_query == "whole milk"


def test_decimal_with_unit():
    r = parse_ingredient("1.5 tbsp olive oil")
    assert r is not None
    assert r.amount == 1.5
    assert r.unit == "tbsp"
    assert r.food_query == "olive oil"


def test_simple_fraction():
    r = parse_ingredient("1/2 cup olive oil")
    assert r is not None
    assert abs(r.amount - 0.5) < 1e-9
    assert r.unit == "cup"
    assert r.food_query == "olive oil"


def test_mixed_fraction():
    r = parse_ingredient("1 1/2 cups flour")
    assert r is not None
    assert abs(r.amount - 1.5) < 1e-9
    assert r.unit == "cups"
    assert r.food_query == "flour"


def test_compact_unit_no_space():
    r = parse_ingredient("100g almonds")
    assert r is not None
    assert r.amount == 100.0
    assert r.unit == "g"
    assert r.food_query == "almonds"


def test_compact_unit_decimal():
    r = parse_ingredient("1.5kg potatoes")
    assert r is not None
    assert r.amount == 1.5
    assert r.unit == "kg"
    assert r.food_query == "potatoes"


def test_no_unit_returns_none_for_unit_field():
    r = parse_ingredient("2 eggs")
    assert r is not None
    assert r.amount == 2.0
    assert r.unit is None
    assert r.food_query == "eggs"


def test_piece_unit():
    r = parse_ingredient("2 large eggs")
    assert r is not None
    assert r.amount == 2.0
    assert r.unit == "large"
    assert r.food_query == "eggs"


def test_cloves():
    r = parse_ingredient("3 cloves garlic")
    assert r is not None
    assert r.amount == 3.0
    assert r.unit == "cloves"
    assert r.food_query == "garlic"


# ---------------------------------------------------------------------------
# parse_ingredient — note and annotation stripping
# ---------------------------------------------------------------------------

def test_slash_annotation_stripped():
    r = parse_ingredient("50g avocado / half an avocado")
    assert r is not None
    assert r.food_query == "avocado"


def test_parenthetical_note_stripped():
    r = parse_ingredient("10g ginger (grated/jarred)")
    assert r is not None
    assert r.food_query == "ginger"


def test_or_alternative_stripped():
    r = parse_ingredient("1 tbsp chicken stock or drippings")
    assert r is not None
    assert r.food_query == "chicken stock"


def test_parenthetical_and_note_combined():
    r = parse_ingredient("50g lemon juice (used 75g, was too much)")
    assert r is not None
    assert r.food_query == "lemon juice"


def test_comma_descriptor_stripped():
    r = parse_ingredient("1 onion, diced")
    assert r is not None
    assert r.food_query == "onion"


def test_comma_descriptor_shallot():
    r = parse_ingredient("1 shallot, diced")
    assert r is not None
    assert r.food_query == "shallot"


def test_comma_descriptor_garlic():
    r = parse_ingredient("4 cloves of garlic, diced")
    assert r is not None
    assert r.food_query == "garlic"


def test_of_preposition_stripped():
    r = parse_ingredient("4 cups of sliced mushrooms")
    assert r is not None
    assert r.unit == "cups"
    assert r.food_query == "sliced mushrooms"


def test_dual_metric_imperial_amount():
    r = parse_ingredient("1.36kg/3 lbs of ground beef (or a mix of beef/veal/pork)")
    assert r is not None
    assert r.amount == 1.36
    assert r.unit == "kg"
    assert r.food_query == "ground beef"


def test_salt_pepper_skipped():
    # "Salt/pepper" has no leading number — should return None
    assert parse_ingredient("Salt/pepper") is None


def test_optional_ingredient_parenthetical():
    r = parse_ingredient("2 tsp Accent (optional)")
    assert r is not None
    assert r.food_query == "Accent"


# ---------------------------------------------------------------------------
# parse_ingredient — Unicode fractions
# ---------------------------------------------------------------------------

def test_unicode_half_fraction():
    r = parse_ingredient("½ tsp salt")
    assert r is not None
    assert abs(r.amount - 0.5) < 1e-9
    assert r.unit == "tsp"
    assert r.food_query == "salt"


def test_unicode_quarter_fraction():
    r = parse_ingredient("¼ cup sugar")
    assert r is not None
    assert abs(r.amount - 0.25) < 1e-9


def test_unicode_three_quarters():
    r = parse_ingredient("¾ cup flour")
    assert r is not None
    assert abs(r.amount - 0.75) < 1e-9


# ---------------------------------------------------------------------------
# parse_ingredient — returns None cases
# ---------------------------------------------------------------------------

def test_blank_line():
    assert parse_ingredient("") is None
    assert parse_ingredient("   ") is None


def test_comment_line():
    assert parse_ingredient("# this is a comment") is None
    assert parse_ingredient("#salt") is None


def test_no_leading_number():
    assert parse_ingredient("salt to taste") is None
    assert parse_ingredient("a pinch of salt") is None


def test_number_only_no_food():
    assert parse_ingredient("1") is None
    assert parse_ingredient("1 cup") is None


# ---------------------------------------------------------------------------
# resolve_grams — direct conversions
# ---------------------------------------------------------------------------

def test_grams_direct():
    grams, warning = resolve_grams(100.0, "g", [])
    assert grams == 100.0
    assert warning is None


def test_kg_conversion():
    grams, warning = resolve_grams(0.5, "kg", [])
    assert grams == 500.0
    assert warning is None


def test_oz_conversion():
    grams, warning = resolve_grams(1.0, "oz", [])
    assert abs(grams - 28.3495) < 0.001
    assert warning is None


def test_lb_conversion():
    grams, warning = resolve_grams(1.0, "lb", [])
    assert abs(grams - 453.592) < 0.001
    assert warning is None


# ---------------------------------------------------------------------------
# resolve_grams — portion lookup
# ---------------------------------------------------------------------------

class _FakePortion:
    """Minimal dict-like stand-in for a sqlite3.Row."""
    def __init__(self, measure_en: str, gram_weight: float):
        self._d = {"measure_en": measure_en, "gram_weight": gram_weight}

    def __getitem__(self, key):
        return self._d[key]


def test_cup_portion_match():
    portions = [_FakePortion("1 cup", 240.0)]
    grams, warning = resolve_grams(2.0, "cup", portions)
    assert grams == 480.0
    assert warning is None


def test_tbsp_portion_match():
    portions = [_FakePortion("1 tbsp", 15.0)]
    grams, warning = resolve_grams(3.0, "tbsp", portions)
    assert grams == 45.0
    assert warning is None


def test_no_portion_fallback():
    grams, warning = resolve_grams(2.0, "cup", [])
    assert grams == 2.0
    assert warning is not None
    assert "cup" in warning


def test_no_unit_with_piece_portion():
    portions = [_FakePortion("1 medium", 120.0)]
    grams, warning = resolve_grams(2.0, None, portions)
    assert grams == 240.0
    assert warning is None


def test_no_unit_no_portions_fallback():
    grams, warning = resolve_grams(3.0, None, [])
    assert grams == 3.0
    assert warning is not None
