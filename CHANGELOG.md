# Changelog

## 0.1.14 — 2026-03-29

- Fixed quality item 6: parser now handles amount-in-parentheses notation (e.g. `garlic powder (½ teaspoon)`)
  - New `_PAREN_AMOUNT_RE` in `parser.py` scans for `food name (amount unit)` when no leading number is found
  - Supports mixed fractions, simple fractions, decimals, and Unicode fractions inside the parenthesis
  - Known unit words (metric, volume, piece) are resolved normally; unrecognised units (e.g. `pinch`) set `unit=None`
  - Lines with non-numeric parentheticals (`to taste`, `big pinch`) continue to return None
  - Item 6 marked done in PLAN.md
- 8 new tests in `tests/test_parser.py` (159 total)

## 0.1.13 — 2026-03-29

- Fixed FTS re-ranking bias toward long compound food names (quality item 4)
  - `search()` now fetches a wider candidate pool (4× limit, min 20) and stable-sorts by whether the food name's first component matches a query word — corrects "Oil, avocado" → "Avocado, raw", "Bread, onion" → "Onion, raw", "Tea, ginger" → "Ginger root, raw"
  - BM25 order preserved as tiebreaker within each group; no regressions for multi-word queries
- Added built-in gram estimates for common piece-count units (quality item 5)
  - `_PIECE_GRAM_ESTIMATES` in `parser.py`: cloves (6g), heads (50g), sprigs (2g), bunches (25g), stalks (40g), ears (150g), strips (15g), leaves (1g)
  - Used as a fallback between food_portion lookup and the 1g last resort; reports "estimated N g each" warning
  - `4 cloves of garlic` now resolves to 24g instead of 4g
- 13 new tests (151 total): 7 in `test_parser.py`, 6 in `test_lookup.py`
- Items 4 and 5 marked done in PLAN.md

## 0.1.12 — 2026-03-29

- Fixed recipe eval table layout: ingredient and match columns now have bounded widths with ellipsis overflow; notes no longer wrap across multiple rows
- `parse_ingredient` now strips leading preparation adjectives (`sliced`, `diced`, `chopped`, `minced`, `grated`, `shredded`, `crushed`, `peeled`, `pitted`, `trimmed`, `halved`, `quartered`) from the food query so "sliced mushrooms" → FTS query "mushrooms"
- `parse_ingredient` now strips inline slash alternatives without surrounding spaces (`lemon/lime juice` → "lemon"); previously only ` / annotation` with spaces was handled
- Adjective stripping is intentionally conservative: "ground", "whole", "fresh", etc. are excluded to preserve canonical food names like "ground beef" and "whole milk"
- 8 new tests in `tests/test_parser.py` (139 total)
- Added quality improvement notes (items 1–6) to PLAN.md

## 0.1.11 — 2026-03-29

- Implemented P5: HTML output (P5 complete)
- New `ew/html.py`: `render_label_html()` and `render_recipe_html()` — complete HTML documents with inline CSS
- Style matches design reference: system-font, minimal borders, bold section headers, indented nutrients, status icons (✓ ✗ △) for recipe ingredients
- `ew lookup --format html` and `ew recipe eval --format html` emit a styled HTML document
- `--output FILE` flag on both commands writes to a file (any format); prints to stdout when omitted
- HTML output escapes all user-derived strings to prevent XSS
- 26 new tests in `tests/test_html.py` (131 total)

## 0.1.10 — 2026-03-28

- Implemented P4: markdown output (P4 complete)
- New `ew/markdown.py`: `render_label_md()` and `render_recipe_md()` — GFM table renderers mirroring the rich console layout
- `ew lookup --format md` outputs a two-column nutrition label as a markdown table
- `ew recipe eval --format md` outputs the ingredient match table and nutrient totals table as markdown
- Both commands default to `--format console` (no behaviour change without the flag)
- 17 new tests in `tests/test_markdown.py` (105 total)
- Removed completed phases P0–P3 from PLAN.md (history is in CHANGELOG)

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
