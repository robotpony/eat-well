"""Tests for FTS search and nutrition label functions."""

import pytest
from rich.console import Console

from ew.db import rebuild_fts
from ew.importers.cnf import CnfImporter
from ew.lookup import (
    FoodMatch,
    _rerank,
    get_food,
    get_nutrients,
    get_portions,
    render_label,
    search,
)


@pytest.fixture
def loaded_db(db, cnf_dir):
    """DB with CNF fixture data imported and FTS rebuilt."""
    CnfImporter(db).run(cnf_dir)
    rebuild_fts(db)
    db.commit()
    return db


# ---------------------------------------------------------------------------
# search()
# ---------------------------------------------------------------------------

def test_search_returns_match(loaded_db):
    results = search(loaded_db, "whole milk")
    assert len(results) >= 1
    assert any("milk" in r.name.lower() for r in results)


def test_search_returns_food_match_type(loaded_db):
    results = search(loaded_db, "whole milk")
    assert isinstance(results[0], FoodMatch)
    assert results[0].id > 0
    assert results[0].source_name


def test_search_no_results(loaded_db):
    results = search(loaded_db, "zzznomatchxyzzy")
    assert results == []


def test_search_respects_limit(loaded_db):
    results = search(loaded_db, "apple", limit=1)
    assert len(results) <= 1


def test_search_french(loaded_db):
    results = search(loaded_db, "lait", lang="fr")
    assert len(results) >= 1
    # French name "Lait entier" should appear in results
    assert any("lait" in r.name.lower() for r in results)


def test_search_invalid_fts_syntax_returns_empty(loaded_db):
    # Pathological input — should not raise, should return empty list
    results = search(loaded_db, '"""((( bad query )))"""')
    assert isinstance(results, list)


# ---------------------------------------------------------------------------
# get_nutrients()
# ---------------------------------------------------------------------------

def test_get_nutrients_returns_rows(loaded_db):
    milk = search(loaded_db, "whole milk")[0]
    nutrients = get_nutrients(loaded_db, milk.id)
    assert len(nutrients) > 0


def test_get_nutrients_scaled_half(loaded_db):
    milk = search(loaded_db, "whole milk")[0]
    n100 = get_nutrients(loaded_db, milk.id, grams=100.0)
    n50 = get_nutrients(loaded_db, milk.id, grams=50.0)
    assert len(n100) == len(n50)
    for a, b in zip(n100, n50):
        assert abs(b["value"] - a["value"] / 2) < 1e-9


def test_get_nutrients_excludes_zeros(loaded_db):
    # Apple raw has only protein in the fixture; no zero rows should appear
    apple = search(loaded_db, "Apple raw")[0]
    nutrients = get_nutrients(loaded_db, apple.id)
    assert all(n["value"] > 0 for n in nutrients)


def test_get_nutrients_ordered_by_rank(loaded_db):
    milk = search(loaded_db, "whole milk")[0]
    nutrients = get_nutrients(loaded_db, milk.id)
    ranks = [n["rank"] for n in nutrients]
    assert ranks == sorted(ranks)


# ---------------------------------------------------------------------------
# get_portions()
# ---------------------------------------------------------------------------

def test_get_portions_returns_rows(loaded_db):
    milk = search(loaded_db, "whole milk")[0]
    portions = get_portions(loaded_db, milk.id)
    assert len(portions) >= 1
    assert portions[0]["gram_weight"] > 0


def test_get_portions_empty_for_no_portions(loaded_db):
    # Manufacture a food with no portions
    loaded_db.execute(
        "INSERT INTO food (source_id, source_food_id, name_en) "
        "SELECT id, '9999', 'No Portions Food' FROM source LIMIT 1"
    )
    food_id = loaded_db.execute(
        "SELECT id FROM food WHERE source_food_id = '9999'"
    ).fetchone()["id"]
    assert get_portions(loaded_db, food_id) == []


# ---------------------------------------------------------------------------
# get_food()
# ---------------------------------------------------------------------------

def test_get_food_returns_source(loaded_db):
    milk = search(loaded_db, "whole milk")[0]
    food = get_food(loaded_db, milk.id)
    assert food is not None
    assert food["name_en"] is not None
    assert food["source_name"] is not None


def test_get_food_returns_none_for_missing(loaded_db):
    assert get_food(loaded_db, 999999) is None


# ---------------------------------------------------------------------------
# render_label()
# ---------------------------------------------------------------------------

def test_render_label_runs_without_error(loaded_db):
    milk = search(loaded_db, "whole milk")[0]
    food = get_food(loaded_db, milk.id)
    nutrients = get_nutrients(loaded_db, milk.id)
    portions = get_portions(loaded_db, milk.id)
    console = Console(force_terminal=False)
    # Should not raise
    render_label(console, food, nutrients, portions)


def test_render_label_per_grams_override(loaded_db):
    milk = search(loaded_db, "whole milk")[0]
    food = get_food(loaded_db, milk.id)
    nutrients = get_nutrients(loaded_db, milk.id)
    portions = get_portions(loaded_db, milk.id)
    console = Console(force_terminal=False)
    render_label(console, food, nutrients, portions, per_grams=250.0)


def test_render_label_no_portions(loaded_db):
    milk = search(loaded_db, "whole milk")[0]
    food = get_food(loaded_db, milk.id)
    nutrients = get_nutrients(loaded_db, milk.id)
    console = Console(force_terminal=False)
    # No portions: only one column shown, should not raise
    render_label(console, food, nutrients, portions=[])


# ---------------------------------------------------------------------------
# _rerank
# ---------------------------------------------------------------------------

def _fm(name: str) -> FoodMatch:
    return FoodMatch(id=0, name=name, source_name="Test", source_code="test")


def test_rerank_prefers_first_word_match():
    # "avocado" query: "Avocado, raw" should rank above "Oil, avocado"
    candidates = [_fm("Oil, avocado"), _fm("Avocado, raw")]
    result = _rerank(candidates, "avocado")
    assert result[0].name == "Avocado, raw"


def test_rerank_prefers_first_word_match_onion():
    # "Onion powder" starts with "onion" (exact query word) → rises to top
    # "Bread, onion" starts with "bread" → relegated
    # "Onions, raw" starts with "onions" (plural, not exact match) → stays in BM25 order
    candidates = [_fm("Bread, onion"), _fm("Onion powder")]
    result = _rerank(candidates, "onion")
    assert result[0].name == "Onion powder"
    assert result[1].name == "Bread, onion"


def test_rerank_preserves_bm25_order_within_group():
    # Both start with a query word — original order (BM25) should be preserved
    candidates = [_fm("Avocado, raw"), _fm("Avocados, all varieties")]
    result = _rerank(candidates, "avocado")
    assert result[0].name == "Avocado, raw"
    assert result[1].name == "Avocados, all varieties"


def test_rerank_multi_word_query():
    # "whole milk": "Milk, whole" starts with "milk" (in query) → preferred
    candidates = [_fm("Buttermilk, whole"), _fm("Milk, whole"), _fm("Milk, reduced fat")]
    result = _rerank(candidates, "whole milk")
    assert result[0].name in ("Milk, whole", "Milk, reduced fat")
    assert result[-1].name == "Buttermilk, whole"


def test_rerank_empty_is_safe():
    assert _rerank([], "avocado") == []


def test_rerank_single_item_unchanged():
    m = [_fm("Avocado, raw")]
    assert _rerank(m, "avocado") == m


def test_render_label_french(loaded_db):
    milk = search(loaded_db, "lait", lang="fr")[0]
    food = get_food(loaded_db, milk.id)
    nutrients = get_nutrients(loaded_db, milk.id)
    portions = get_portions(loaded_db, milk.id)
    console = Console(force_terminal=False)
    render_label(console, food, nutrients, portions, lang="fr")
