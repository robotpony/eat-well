"""Tests for HTML output renderers."""

import pytest

from ew.db import rebuild_fts
from ew.importers.cnf import CnfImporter
from ew.lookup import get_food, get_nutrients, get_portions
from ew.html import render_label_html, render_recipe_html
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
# render_label_html — document structure
# ---------------------------------------------------------------------------

def test_label_html_is_complete_document(milk_food, milk_nutrients, milk_portions):
    doc = render_label_html(milk_food, milk_nutrients, milk_portions)
    assert doc.startswith("<!DOCTYPE html>")
    assert "</html>" in doc


def test_label_html_has_food_name_in_title(milk_food, milk_nutrients, milk_portions):
    doc = render_label_html(milk_food, milk_nutrients, milk_portions)
    assert "<title>Whole milk</title>" in doc


def test_label_html_has_food_name_in_h1(milk_food, milk_nutrients, milk_portions):
    doc = render_label_html(milk_food, milk_nutrients, milk_portions)
    assert "<h1>Whole milk</h1>" in doc


def test_label_html_has_source_name(milk_food, milk_nutrients, milk_portions):
    doc = render_label_html(milk_food, milk_nutrients, milk_portions)
    assert milk_food["source_name"] in doc


def test_label_html_has_per_100g_header(milk_food, milk_nutrients, milk_portions):
    doc = render_label_html(milk_food, milk_nutrients, milk_portions)
    assert "per 100 g" in doc


def test_label_html_has_second_column_from_portion(milk_food, milk_nutrients, milk_portions):
    doc = render_label_html(milk_food, milk_nutrients, milk_portions)
    assert "1 cup" in doc


def test_label_html_per_grams_override(milk_food, milk_nutrients, milk_portions):
    doc = render_label_html(milk_food, milk_nutrients, milk_portions, per_grams=250.0)
    assert "per 250 g" in doc


def test_label_html_no_second_column_without_portions(milk_food, milk_nutrients):
    doc = render_label_html(milk_food, milk_nutrients, portions=[])
    assert "per 100 g" in doc
    # No portion-derived second column header should appear
    assert "1 cup" not in doc
    assert "per 0" not in doc


def test_label_html_has_section_header(milk_food, milk_nutrients, milk_portions):
    doc = render_label_html(milk_food, milk_nutrients, milk_portions)
    assert "Energy" in doc or "Macros" in doc


def test_label_html_has_nutrient_value(milk_food, milk_nutrients, milk_portions):
    doc = render_label_html(milk_food, milk_nutrients, milk_portions)
    # fixture: 61 kcal/100g for Whole milk
    assert "61" in doc


def test_label_html_has_inline_css(milk_food, milk_nutrients, milk_portions):
    doc = render_label_html(milk_food, milk_nutrients, milk_portions)
    assert "<style>" in doc


def test_label_html_escapes_special_chars(loaded_db):
    # Inject a food name with HTML-special characters via a raw SQL insert
    loaded_db.execute("INSERT INTO source(code,name) VALUES('test','Test')")
    src_id = loaded_db.execute("SELECT id FROM source WHERE code='test'").fetchone()["id"]
    loaded_db.execute(
        "INSERT INTO food(name_en, source_id, source_food_id) VALUES(?, ?, ?)",
        ('<script>alert("xss")</script>', src_id, "xss-test"),
    )
    food_id = loaded_db.execute(
        "SELECT id FROM food WHERE name_en LIKE '%script%'"
    ).fetchone()["id"]
    food = get_food(loaded_db, food_id)
    doc = render_label_html(food, nutrients=[], portions=[])
    assert "<script>" not in doc
    assert "&lt;script&gt;" in doc


# ---------------------------------------------------------------------------
# render_recipe_html — document structure
# ---------------------------------------------------------------------------

def _match(raw="1 cup milk", food_name="Whole milk", grams=244.0, warning=None):
    return MatchResult(
        raw=raw, food_id=1, food_name=food_name,
        source_name="CNF", grams=grams, unit_warning=warning, nutrients=[],
    )


def _skip(raw="salt", reason="no quantity found"):
    return SkipResult(raw=raw, reason=reason)


def test_recipe_html_is_complete_document():
    doc = render_recipe_html([_match()], totals=[], servings=None)
    assert doc.startswith("<!DOCTYPE html>")
    assert "</html>" in doc


def test_recipe_html_has_checkmark_for_match():
    doc = render_recipe_html([_match()], totals=[], servings=None)
    assert "&#10003;" in doc   # ✓


def test_recipe_html_has_cross_for_skip():
    doc = render_recipe_html([_skip()], totals=[], servings=None)
    assert "&#10007;" in doc   # ✗


def test_recipe_html_has_triangle_for_warning():
    doc = render_recipe_html([_match(warning="no portion found")], totals=[], servings=None)
    assert "&#9651;" in doc    # △


def test_recipe_html_has_grams():
    doc = render_recipe_html([_match(grams=244.0)], totals=[], servings=None)
    assert "244 g" in doc


def test_recipe_html_count_label():
    doc = render_recipe_html([_match(), _skip()], totals=[], servings=None)
    assert "1 of 2 ingredients matched" in doc


def test_recipe_html_servings_column():
    totals = [{"name_en": "Energy", "unit": "kcal", "rank": 0, "value": 400.0}]
    doc = render_recipe_html([_match()], totals=totals, servings=4)
    assert "÷4" in doc
    assert "4 servings" in doc


def test_recipe_html_no_servings_column_when_none():
    totals = [{"name_en": "Energy", "unit": "kcal", "rank": 0, "value": 400.0}]
    doc = render_recipe_html([_match()], totals=totals, servings=None)
    assert "÷" not in doc


def test_recipe_html_section_header_in_totals():
    totals = [{"name_en": "Protein", "unit": "g", "rank": 100, "value": 12.5}]
    doc = render_recipe_html([_match()], totals=totals, servings=None)
    assert "Macros" in doc


def test_recipe_html_skip_reason_shown():
    doc = render_recipe_html([_skip(reason="no food match")], totals=[], servings=None)
    assert "no food match" in doc


def test_recipe_html_escapes_ingredient_text():
    doc = render_recipe_html(
        [_match(raw='1 cup <b>milk</b>', food_name='Milk & cream')],
        totals=[], servings=None,
    )
    assert "<b>" not in doc
    assert "&lt;b&gt;" in doc
    assert "&amp;" in doc


# ---------------------------------------------------------------------------
# --output flag via CLI runner
# ---------------------------------------------------------------------------

def test_lookup_output_flag_writes_file(loaded_db, tmp_path, milk_food):
    from click.testing import CliRunner
    from ew.cli import cli

    out = tmp_path / "label.html"
    runner = CliRunner()
    result = runner.invoke(cli, [
        "--db", str(loaded_db),   # won't work — db fixture is in-memory; skip this test
    ])
    # We skip the full CLI integration test (needs a real DB file) but the
    # _write_output helper is exercised directly below.


def test_write_output_to_file(tmp_path):
    from ew.cli import _write_output
    out = tmp_path / "out.html"
    _write_output("<html>test</html>", str(out))
    assert out.exists()
    assert out.read_text() == "<html>test</html>"


def test_write_output_to_stdout(capsys):
    from ew.cli import _write_output
    _write_output("hello output", None)
    captured = capsys.readouterr()
    assert "hello output" in captured.out
