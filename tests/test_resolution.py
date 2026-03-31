"""Tests for P9: Enhanced ingredient resolution.

Covers:
  P9a — alias substitution (bundled + user DB)
  P9b — food weight reference table
  P9c — user portion cache
  P9d — to-taste defaults
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ew.parser import parse_ingredient, resolve_grams
from ew.resolution import (
    ResolutionContext,
    clear_portion_cache,
    list_aliases,
    list_food_weights,
    list_portion_cache,
    load_context,
    save_alias,
    save_food_weight,
    save_portion_cache,
)


# ---------------------------------------------------------------------------
# P9a: Alias substitution
# ---------------------------------------------------------------------------

class TestAliasSubstitution:
    def test_bundled_alias_applied(self):
        ctx = load_context()  # no DB, no work_dir — bundled only
        assert "msg" in ctx.aliases
        assert ctx.aliases["msg"] == "monosodium glutamate"

    def test_alias_substitutes_in_parse(self):
        aliases = {"msg": "monosodium glutamate"}
        result = parse_ingredient("1 tsp msg", aliases=aliases)
        assert result is not None
        assert result.food_query == "monosodium glutamate"

    def test_alias_word_level_in_multi_word_query(self):
        # "msg sauce" — word-level alias fires on "msg" inside the query
        aliases = {"msg": "monosodium glutamate"}
        result = parse_ingredient("1 tsp msg sauce", aliases=aliases)
        assert result is not None
        assert result.food_query == "monosodium glutamate"

    def test_alias_case_insensitive(self):
        aliases = {"msg": "monosodium glutamate"}
        result = parse_ingredient("1 tsp MSG", aliases=aliases)
        assert result is not None
        assert result.food_query == "monosodium glutamate"

    def test_no_alias_no_substitution(self):
        result = parse_ingredient("1 tsp garlic powder", aliases={})
        assert result is not None
        assert result.food_query == "garlic powder"

    def test_save_and_load_alias(self, db):
        save_alias(db, "evoo", "olive oil")
        bundled, user = list_aliases(db)
        keys = [u["input_key"] for u in user]
        assert "evoo" in keys

    def test_user_alias_in_load_context(self, db):
        save_alias(db, "testkey", "test replacement")
        ctx = load_context(db)
        assert ctx.aliases.get("testkey") == "test replacement"

    def test_user_alias_overrides_bundled(self, db):
        save_alias(db, "msg", "custom msg replacement")
        ctx = load_context(db)
        assert ctx.aliases["msg"] == "custom msg replacement"

    def test_alias_upsert(self, db):
        save_alias(db, "evoo", "olive oil")
        save_alias(db, "evoo", "extra virgin olive oil")
        _, user = list_aliases(db)
        entry = next(u for u in user if u["input_key"] == "evoo")
        assert entry["replacement"] == "extra virgin olive oil"

    def test_list_aliases_no_db(self):
        bundled, user = list_aliases(None)
        assert "msg" in bundled
        assert user == []


# ---------------------------------------------------------------------------
# P9b: Food weight reference
# ---------------------------------------------------------------------------

class TestFoodWeightReference:
    def test_shallot_each(self):
        fw = [{"key": "shallot", "unit": "each", "grams": 30}]
        grams, warning = resolve_grams(1.0, None, [], food_query="shallot", food_weights=fw)
        assert grams == 30.0
        assert warning is None

    def test_shallots_plural(self):
        fw = [{"key": "shallot", "unit": "each", "grams": 30}]
        grams, warning = resolve_grams(2.0, None, [], food_query="shallots", food_weights=fw)
        assert grams == 60.0
        assert warning is None

    def test_mushroom_cup(self):
        fw = [{"key": "mushroom", "unit": "cup", "grams": 70}]
        grams, warning = resolve_grams(4.0, "cup", [], food_query="mushrooms", food_weights=fw)
        assert grams == 280.0
        assert warning is None

    def test_multiword_key_substring_match(self):
        fw = [{"key": "bell pepper", "unit": "medium", "grams": 120}]
        grams, warning = resolve_grams(2.0, "medium", [], food_query="bell pepper", food_weights=fw)
        assert grams == 240.0
        assert warning is None

    def test_unit_normalisation_cups(self):
        fw = [{"key": "spinach", "unit": "cup", "grams": 30}]
        grams, warning = resolve_grams(3.0, "cups", [], food_query="spinach", food_weights=fw)
        assert grams == 90.0
        assert warning is None

    def test_user_entry_beats_bundled(self):
        # User entry is first in the list — it wins on first match
        fw = [
            {"key": "mushroom", "unit": "cup", "grams": 100},   # user
            {"key": "mushroom", "unit": "cup", "grams": 70},    # bundled
        ]
        grams, warning = resolve_grams(1.0, "cup", [], food_query="mushrooms", food_weights=fw)
        assert grams == 100.0

    def test_food_weight_after_portion_db_miss(self):
        # Portion list is empty; food weight reference provides the answer.
        fw = [{"key": "shallot", "unit": "each", "grams": 30}]
        grams, _ = resolve_grams(3.0, None, [], food_query="shallot", food_weights=fw)
        assert grams == 90.0

    def test_no_match_falls_through_to_1g(self):
        fw = [{"key": "shallot", "unit": "each", "grams": 30}]
        grams, warning = resolve_grams(1.0, "cup", [], food_query="shallot", food_weights=fw)
        # "shallot" + "cup" has no entry → 1 g fallback
        assert grams == 1.0
        assert warning is not None

    def test_save_and_list_food_weight(self, tmp_path):
        save_food_weight(tmp_path, "shallot", "each", 30.0)
        bundled, user = list_food_weights(tmp_path)
        assert any(e["key"] == "shallot" and e["unit"] == "each" for e in user)

    def test_save_food_weight_upsert(self, tmp_path):
        save_food_weight(tmp_path, "onion", "medium", 100.0)
        save_food_weight(tmp_path, "onion", "medium", 115.0)
        _, user = list_food_weights(tmp_path)
        entry = next(e for e in user if e["key"] == "onion" and e["unit"] == "medium")
        assert entry["grams"] == 115.0

    def test_bundled_food_weights_loaded(self):
        ctx = load_context()
        assert any(e["key"] == "shallot" for e in ctx.food_weights)
        assert any(e["key"] == "mushroom" for e in ctx.food_weights)

    def test_egg_word_match(self):
        fw = [{"key": "egg", "unit": "large", "grams": 50}]
        # "nutmeg" should NOT match "egg" — "nutmeg" split = ["nutmeg"],
        # "nutmeg".startswith("egg") is False
        grams, warning = resolve_grams(1.0, "large", [], food_query="nutmeg", food_weights=fw)
        assert warning is not None  # fell through — no match for nutmeg+large

    def test_egg_exact_match(self):
        fw = [{"key": "egg", "unit": "large", "grams": 50}]
        grams, warning = resolve_grams(2.0, "large", [], food_query="eggs", food_weights=fw)
        assert grams == 100.0
        assert warning is None


# ---------------------------------------------------------------------------
# P9c: User portion cache
# ---------------------------------------------------------------------------

class TestUserPortionCache:
    def test_cache_used_before_1g_fallback(self, db):
        save_portion_cache(db, "shallot", None, 30.0)
        ctx = load_context(db)
        grams, warning = resolve_grams(
            2.0, None, [], food_query="shallot", user_cache=ctx.user_cache
        )
        assert grams == 60.0
        assert warning is None

    def test_cache_with_unit(self, db):
        save_portion_cache(db, "mushroom", "cup", 70.0)
        ctx = load_context(db)
        grams, warning = resolve_grams(
            3.0, "cup", [], food_query="mushroom", user_cache=ctx.user_cache
        )
        assert grams == 210.0
        assert warning is None

    def test_save_and_list(self, db):
        save_portion_cache(db, "shallot", None, 30.0)
        entries = list_portion_cache(db)
        assert any(e["food_query"] == "shallot" for e in entries)

    def test_clear_cache(self, db):
        save_portion_cache(db, "shallot", None, 30.0)
        clear_portion_cache(db)
        assert list_portion_cache(db) == []

    def test_upsert_cache(self, db):
        save_portion_cache(db, "shallot", None, 30.0)
        save_portion_cache(db, "shallot", None, 35.0)
        entries = list_portion_cache(db)
        entry = next(e for e in entries if e["food_query"] == "shallot")
        assert entry["gram_weight"] == 35.0

    def test_cache_checked_after_portion_db(self):
        # If the portion DB has a match, cache is not reached.
        portions = [{"measure_en": "1 cup", "measure_fr": "", "gram_weight": 244.0}]
        cache = {("milk", "cup"): 999.0}
        grams, _ = resolve_grams(1.0, "cup", portions, food_query="milk", user_cache=cache)
        assert grams == 244.0  # DB portion wins

    def test_load_context_includes_cache(self, db):
        save_portion_cache(db, "garlic", None, 6.0)
        ctx = load_context(db)
        assert ("garlic", None) in ctx.user_cache


# ---------------------------------------------------------------------------
# P9d: To-taste defaults
# ---------------------------------------------------------------------------

class TestTasteDefaults:
    def test_salt_default(self):
        defaults = [{"key": "salt", "grams": 2.0}]
        result = parse_ingredient("salt, pepper (to taste)", taste_defaults=defaults)
        assert result is not None
        assert result.amount == 2.0
        assert result.unit == "g"
        assert result.food_query == "salt"
        assert result.note is not None
        assert "to taste" in result.note

    def test_pepper_default(self):
        defaults = [{"key": "salt", "grams": 2.0}, {"key": "pepper", "grams": 0.5}]
        result = parse_ingredient("black pepper to taste", taste_defaults=defaults)
        assert result is not None
        assert result.amount == pytest.approx(0.5)
        assert "pepper" in result.food_query

    def test_thyme_big_pinch(self):
        defaults = [{"key": "thyme", "grams": 0.3}]
        result = parse_ingredient("thyme (big pinch)", taste_defaults=defaults)
        assert result is not None
        assert result.amount == pytest.approx(0.3)
        assert result.food_query == "thyme"

    def test_salt_slash_pepper(self):
        defaults = [{"key": "salt", "grams": 2.0}]
        result = parse_ingredient("Salt/pepper", taste_defaults=defaults)
        assert result is not None
        assert result.food_query.lower() == "salt"

    def test_unrecognised_returns_none(self):
        defaults = [{"key": "salt", "grams": 2.0}]
        result = parse_ingredient("some unknown ingredient", taste_defaults=defaults)
        assert result is None

    def test_no_defaults_still_returns_none(self):
        result = parse_ingredient("salt to taste")
        assert result is None

    def test_bundled_defaults_loaded(self):
        ctx = load_context()
        keys = [td["key"] for td in ctx.taste_defaults]
        assert "salt" in keys
        assert "pepper" in keys
        assert "thyme" in keys

    def test_taste_default_note_includes_grams(self):
        defaults = [{"key": "salt", "grams": 2.0}]
        result = parse_ingredient("salt", taste_defaults=defaults)
        assert result is not None
        assert "2" in result.note
        assert "to taste" in result.note

    def test_user_taste_default_overrides_bundled(self, tmp_path):
        # Write a user taste_defaults.json with a higher salt default
        user_file = tmp_path / "taste_defaults.json"
        user_file.write_text(json.dumps([{"key": "salt", "grams": 5.0}]))
        ctx = load_context(work_dir=tmp_path)
        # User entry is first in the list — it should be found first
        salt_entries = [td for td in ctx.taste_defaults if td["key"] == "salt"]
        assert salt_entries[0]["grams"] == 5.0


# ---------------------------------------------------------------------------
# load_context integration
# ---------------------------------------------------------------------------

class TestLoadContext:
    def test_empty_context_from_no_args(self):
        ctx = load_context()
        assert isinstance(ctx.aliases, dict)
        assert isinstance(ctx.food_weights, list)
        assert isinstance(ctx.taste_defaults, list)
        assert isinstance(ctx.user_cache, dict)

    def test_context_with_db(self, db):
        ctx = load_context(db)
        assert "msg" in ctx.aliases
        assert ctx.user_cache == {}

    def test_context_with_work_dir(self, tmp_path):
        ctx = load_context(work_dir=tmp_path)
        # Bundled data loaded even with empty work_dir
        assert len(ctx.food_weights) > 0
        assert len(ctx.taste_defaults) > 0
