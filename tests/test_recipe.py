"""Tests for recipe aggregation."""

import pytest

from ew.recipe import MatchResult, SkipResult, aggregate


class _Row:
    """Minimal dict-like stand-in for sqlite3.Row."""
    def __init__(self, **kw):
        self._d = kw

    def __getitem__(self, key):
        return self._d[key]


def _rows(*items):
    """Build a list of _Row objects from (name_en, unit, rank, value) tuples."""
    return [_Row(name_en=n, unit=u, rank=r, value=v) for n, u, r, v in items]


# ---------------------------------------------------------------------------
# aggregate()
# ---------------------------------------------------------------------------

def test_aggregate_single_ingredient():
    nutrient_list = [_rows(("Protein", "g", 100, 5.0), ("Energy (kcal)", "kcal", 10, 200.0))]
    result = aggregate(nutrient_list)
    assert len(result) == 2
    by_name = {r["name_en"]: r for r in result}
    assert by_name["Protein"]["value"] == 5.0
    assert by_name["Energy (kcal)"]["value"] == 200.0


def test_aggregate_sums_across_ingredients():
    lists = [
        _rows(("Protein", "g", 100, 5.0), ("Energy (kcal)", "kcal", 10, 100.0)),
        _rows(("Protein", "g", 100, 3.0), ("Energy (kcal)", "kcal", 10, 80.0)),
    ]
    result = aggregate(lists)
    by_name = {r["name_en"]: r for r in result}
    assert by_name["Protein"]["value"] == pytest.approx(8.0)
    assert by_name["Energy (kcal)"]["value"] == pytest.approx(180.0)


def test_aggregate_merges_same_nutrient_different_foods():
    # Same nutrient name appearing in both ingredient lists
    lists = [
        _rows(("Total fat", "g", 200, 14.0)),
        _rows(("Total fat", "g", 200, 2.5)),
    ]
    result = aggregate(lists)
    assert len(result) == 1
    assert result[0]["value"] == pytest.approx(16.5)


def test_aggregate_ordered_by_rank():
    lists = [_rows(
        ("Sodium", "mg", 400, 100.0),
        ("Protein", "g", 100, 5.0),
        ("Energy (kcal)", "kcal", 10, 200.0),
    )]
    result = aggregate(lists)
    ranks = [r["rank"] for r in result]
    assert ranks == sorted(ranks)


def test_aggregate_empty_returns_empty():
    assert aggregate([]) == []


def test_aggregate_excludes_zero_rows():
    # get_nutrients already excludes zeros, but aggregate itself
    # should handle a list with a 0-value row gracefully.
    lists = [_rows(("Protein", "g", 100, 0.0))]
    result = aggregate(lists)
    # Zero values are summed in; filtering happens upstream in get_nutrients.
    assert result[0]["value"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# MatchResult / SkipResult dataclasses
# ---------------------------------------------------------------------------

def test_match_result_fields():
    r = MatchResult(
        raw="1 cup milk",
        food_id=42,
        food_name="Milk, whole",
        source_name="USDA SR Legacy",
        grams=244.0,
        unit_warning=None,
        nutrients=[],
    )
    assert r.food_id == 42
    assert r.grams == 244.0
    assert r.unit_warning is None


def test_skip_result_fields():
    r = SkipResult(raw="salt to taste", reason="no quantity found")
    assert r.raw == "salt to taste"
    assert r.reason == "no quantity found"
