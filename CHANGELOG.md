# Changelog

## 0.1.9 — 2026-03-28

- Fixed three parser bugs that caused most `beef-base.md` ingredients to return zero FTS results
- `parse_ingredient` now strips leading `of ` preposition after unit extraction (`4 cups of sliced mushrooms` → food_query `sliced mushrooms`)
- `parse_ingredient` now strips `, preparation note` after the first comma (`1 onion, diced` → `onion`)
- `parse_ingredient` now strips leading alternative-amount prefix from dual metric/imperial notation (`1.36kg/3 lbs of ground beef` → food_query `ground beef`)
- Fixed unit-alternation ordering in `_LEADING_ALT_AMOUNT_RE` so `lbs` is matched before the bare `l` (litre) alternative
- `_NOTE_PATTERNS` parenthetical match now applies anywhere in the string, not only at the end
- 8 new tests in `tests/test_parser.py` (88 total, all passing)

## 0.1.8 — 2026-03-28

- Fixed parser dropping real-world recipe annotations that caused FTS to return zero results
- `parse_ingredient` now strips trailing ` / annotation` (e.g. "50g avocado / half an avocado")
- `parse_ingredient` now strips trailing parenthetical notes (e.g. "10g ginger (grated/jarred)")
- `parse_ingredient` now strips trailing ` or alternative` (e.g. "1 tbsp stock or water")
- Unicode fraction characters (½ ¼ ¾ ⅓ ⅔ etc.) are now normalised to ASCII before parsing
- 7 new tests in `tests/test_parser.py` (81 total)
- Renamed `example-recipes/avacado-dressing.md` → `avocado-dressing.md`

## 0.1.7 — 2026-03-28

- Added `ew match INGREDIENT` command (P2 complete)
- Added `ew recipe eval FILE` command with `--servings N` flag
- New `ew/parser.py`: ingredient string parsing (integers, decimals, fractions, compact `100g` form) and unit-to-gram resolution (direct metric + food_portion fuzzy match + 1 g fallback)
- New `ew/recipe.py`: `MatchResult`/`SkipResult` dataclasses and `aggregate()` for summing nutrients across ingredients
- `SECTIONS` and `fmt_value` in `lookup.py` made public for reuse in recipe rendering
- 30 new tests in `tests/test_parser.py` and `tests/test_recipe.py` (74 total)
- P2 marked done in PLAN.md and README

## 0.1.6 — 2026-03-28

- Added annotated example output to the README lookup section (dark chocolate, 70-85% cacao)

## 0.1.5 — 2026-03-28

- Rewrote README to focus on setup and usage; removed phases and aspirational features list
- Added `setup` script — creates venv and installs the package in one step
- Data download instructions moved entirely to `import/README.md`

## 0.1.4 — 2026-03-28

- Added `ew lookup QUERY` command (P1 complete)
- FTS5 BM25 search with column-filtered, safely tokenised queries
- Two-column nutrition label (per 100 g + per first portion) grouped into Energy / Macros / Minerals / Vitamins sections
- `--pick N` to auto-select a result without prompting
- `--per GRAMS` to override the second column scale
- `--lang fr` for French search and display (CNF foods only)
- 18 new tests in `tests/test_lookup.py` (44 total)
- P1 marked done in PLAN.md and README

## 0.1.3 — 2026-03-28

- Rewrote `ew import` output using rich: section rules, coloured counts, named sources, and a summary footer
- Source names now shown in full (e.g. "Canadian Food Nutrient Database") instead of raw codes
- Skipped sources shown dim on one line instead of interleaved with import progress
- Counts display foods, portions, and categories; dropped `food_nutrient` (too large, not useful at a glance)
- Removed `try/except ImportError` fallback in `sources` command (rich is a hard dependency)

## 0.1.2 — 2026-03-28

- Default database path changed from `ew.db` (project root) to `work/ew.db`
- `work/` directory is created automatically on first import and is git-ignored
- Updated README to document the new default path

## 0.1.1 — 2026-03-28

- Rewrote README with clear setup instructions, expected data directory structure, and download guidance for CNF and USDA datasets
- Fixed typos in project description (aggregate, absorption, glycemic)
- Added status table to track phase progress

## 0.1.0 — 2026-03-26

- Initial implementation of Phase 0 (P0)
- SQLite schema: source, nutrient, food_category, food, food_nutrient, food_portion, FTS5 index
- CNF importer (Canadian Food Nutrient Database 2015): food groups, nutrients with French names, foods, nutrient amounts, portion measures
- USDA importer for three FoodData Central datasets: Foundation Foods, SR Legacy (zip), Survey/FNDDS (zip)
- Nutrient deduplication across sources via shared USDA SR numbering system
- `ew import` and `ew sources` CLI commands
- 26 unit tests using in-memory fixtures
