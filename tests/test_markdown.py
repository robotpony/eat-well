"""Tests for markdown output renderers."""

import pytest

from ew.db import rebuild_fts
from ew.importers.cnf import CnfImporter
from ew.lookup import get_food, get_nutrients, get_portions
from ew.markdown import render_label_md, render_recipe_md
from ew.recipe import MatchResult, SkipResult


@pytest.fixture
def loaded_db(db, cnf_dir):
    CnfImporter(db).run(cnf_dir)
    rebuild_fts(db)
    db.commit()
    return db


@pytest.fixture
def milk_food(loaded_db):
    row = loaded_db.execute("SELECT id FROM food WHERE name_en = 'Whole milk'").fetchone()
    return get_food(loaded_db, row["id"])


@pytest.fixture
def milk_nutrients(loaded_db, milk_food):
    return get_nutrients(loaded_db, milk_food["id"])


@pytest.fixture
def milk_portions(loaded_db, milk_food):
    return get_portions(loaded_db, milk_food["id"])


# ---------------------------------------------------------------------------
# render_label_md — structure
# ---------------------------------------------------------------------------

def test_label_md_has_heading(milk_food, milk_nutrients, milk_portions):
    md = render_label_md(milk_food, milk_nutrients, milk_portions)
    assert "## Whole milk" in md


def test_label_md_has_per_100g_column(milk_food, milk_nutrients, milk_portions):
    md = render_label_md(milk_food, milk_nutrients, milk_portions)
    assert "per 100 g" in md


def test_label_md_has_second_column_from_portion(milk_food, milk_nutrients, milk_portions):
    md = render_label_md(milk_food, milk_nutrients, milk_portions)
    # first portion is "1 cup" — should appear as second column header
    assert "1 cup" in md


def test_label_md_no_second_column_when_no_portions(milk_food, milk_nutrients):
    md = render_label_md(milk_food, milk_nutrients, portions=[])
    lines = md.splitlines()
    # header row should have exactly two columns (Nutrient + per 100 g)
    header = next(l for l in lines if "per 100 g" in l)
    assert header.count("|") == 3  # | Nutrient | per 100 g |


def test_label_md_per_grams_override(milk_food, milk_nutrients, milk_portions):
    md = render_label_md(milk_food, milk_nutrients, milk_portions, per_grams=250.0)
    assert "per 250 g" in md


def test_label_md_has_section_headers(milk_food, milk_nutrients, milk_portions):
    md = render_label_md(milk_food, milk_nutrients, milk_portions)
    # fixture has Energy (rank 208→mapped) and Protein
    assert "**Energy**" in md or "**Macros**" in md


def test_label_md_nutrient_values_present(milk_food, milk_nutrients, milk_portions):
    md = render_label_md(milk_food, milk_nutrients, milk_portions)
    # Whole milk fixture has 61 kcal/100g — should appear somewhere
    assert "61" in md


def test_label_md_nbsp_indentation(milk_food, milk_nutrients, milk_portions):
    md = render_label_md(milk_food, milk_nutrients, milk_portions)
    assert "&nbsp;&nbsp;" in md


def test_label_md_is_valid_gfm_table(milk_food, milk_nutrients, milk_portions):
    md = render_label_md(milk_food, milk_nutrients, milk_portions)
    lines = [l for l in md.splitlines() if l.startswith("|")]
    assert len(lines) >= 2  # at least header + separator
    # separator row must have ---
    assert any("---" in l for l in lines)


# ---------------------------------------------------------------------------
# render_recipe_md — structure
# ---------------------------------------------------------------------------

def _make_match(raw="1 cup milk", food_name="Whole milk", grams=244.0, warning=None):
    return MatchResult(
        raw=raw,
        food_id=1,
        food_name=food_name,
        source_name="CNF",
        grams=grams,
        unit_warning=warning,
        nutrients=[],
    )


def _make_skip(raw="salt", reason="no quantity found"):
    return SkipResult(raw=raw, reason=reason)


def test_recipe_md_has_ingredient_table():
    results = [_make_match(), _make_skip()]
    md = render_recipe_md(results, totals=[])
    assert "Ingredient" in md
    assert "Match" in md


def test_recipe_md_matched_row_has_checkmark():
    results = [_make_match()]
    md = render_recipe_md(results, totals=[])
    assert "✓" in md


def test_recipe_md_skip_row_has_cross():
    results = [_make_skip()]
    md = render_recipe_md(results, totals=[])
    assert "✗" in md


def test_recipe_md_warning_shows_warning_icon():
    results = [_make_match(warning="no portion found for 'cup'")]
    md = render_recipe_md(results, totals=[])
    assert "⚠" in md


def test_recipe_md_count_label():
    results = [_make_match(), _make_skip()]
    md = render_recipe_md(results, totals=[])
    assert "1 of 2 ingredients matched" in md


def test_recipe_md_per_portion_column_default():
    totals = [{"name_en": "Energy (kcal)", "unit": "kCal", "rank": 0, "value": 400.0}]
    results = [_make_match()]
    md = render_recipe_md(results, totals=totals)
    assert "Per 150 g" in md


def test_recipe_md_per_portion_custom_label():
    totals = [{"name_en": "Energy (kcal)", "unit": "kCal", "rank": 0, "value": 400.0}]
    results = [_make_match()]
    md = render_recipe_md(results, totals=totals, portion_label="Per serving (÷4, 61 g)", portion_factor=0.25)
    assert "Per serving (÷4, 61 g)" in md


def test_recipe_md_per_portion_value_scaled():
    # total 400 kcal × factor 0.25 = 100 kcal per portion
    totals = [{"name_en": "Energy", "unit": "kcal", "rank": 0, "value": 400.0}]
    results = [_make_match()]
    md = render_recipe_md(results, totals=totals, portion_label="Per serving", portion_factor=0.25)
    assert "100 kcal" in md


def test_recipe_md_total_column_shows_grams():
    # _make_match defaults to grams=244.0; header should include that weight
    totals = [{"name_en": "Energy", "unit": "kcal", "rank": 0, "value": 100.0}]
    results = [_make_match(grams=244.0)]
    md = render_recipe_md(results, totals=totals)
    assert "Total (244 g)" in md


def test_recipe_md_totals_section_present():
    totals = [{"name_en": "Protein", "unit": "g", "rank": 100, "value": 12.5}]
    results = [_make_match()]
    md = render_recipe_md(results, totals=totals)
    assert "Totals" in md
    assert "Protein" in md
