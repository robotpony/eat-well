# Changelog

## 0.1.21 — 2026-03-30

- Total recipe gram weight now shown in the "Total" column header of `ew recipe eval`
  - Console: `Total (2,056 g)`; markdown and HTML renderers derive the weight directly from matched ingredient grams
  - 2 new tests in `test_markdown.py` and `test_html.py` (212 total)

## 0.1.20 — 2026-03-30

- Added per-portion column to `ew recipe eval` (always visible)
  - Defaults to 150 g when no flag is given: `"Per 150 g"`
  - `--servings N` computes actual gram weight per serving from total recipe weight ÷ N; label shows e.g. `"Per serving (÷4, 343 g)"`
  - `--portion GRAMS` sets the gram weight directly: `"Per 250 g"`
  - `--portion` takes precedence over `--servings` when both are given
  - Per-portion value = total nutrient × (portion_grams / total_recipe_grams)
  - Updated `render_recipe_md` and `render_recipe_html` signatures: replaced `servings: Optional[int]` with `portion_label: str` + `portion_factor: float`
- 6 new/updated tests in `test_markdown.py` and `test_html.py` (210 total)

## 0.1.19 — 2026-03-30

- Fixed USDA Survey (FNDDS) foods having 0 nutrients, causing wildly low recipe energy totals
  - Root cause: Survey `food_nutrient.csv` stores `nutrient_nbr` (e.g. `208` for Energy) in its `nutrient_id` column, while Foundation and SR Legacy use the USDA `id` column (e.g. `1008`); the importer's lookup map was keyed only by USDA id, so every Survey nutrient lookup silently missed
  - Fix: `_import_nutrients()` now builds a second map `_nutrient_nbr_map` keyed by `sr_nbr`; `_import_food_nutrients()` tries the USDA-id map first then falls back to the sr_nbr map
  - Re-running `ew import` adds the 365,560 previously-missing nutrient rows for 5,624 Survey foods; no existing data is duplicated (UNIQUE constraint + INSERT OR IGNORE)
  - `beef-base.md` now totals ~3,660 kcal instead of 112 kcal
- 2 new tests in `tests/test_importers.py` (208 total)

## 0.1.18 — 2026-03-29

- Fixed two bugs in `_clean_food_query()` that caused "2 tsp Accent MSG (optional)" to produce no match
  - **Word-level alias substitution**: step 6 now falls back to matching each word in the cleaned query against the alias table, so `"Accent MSG"` triggers the `"msg"` → `"monosodium glutamate"` alias; exact-match still takes priority when available
  - **Post-parenthetical "of " strip**: added step 3b that re-strips a leading `"of "` after parenthetical removal; previously `"(3 lbs) of ground beef"` left `"of ground beef"` because step 2 ran before the parenthetical was gone
- Updated `test_resolution.py`: `test_alias_applied_after_cleaning` renamed and corrected to reflect new word-level behaviour
- 4 new tests in `tests/test_parser.py` (206 total)

## 0.1.17 — 2026-03-29

- Fixed root cause of "onion" → "Onion dip" mismatch (qol)
  - `_build_fts_query()` now emits prefix queries (`"onion"*`) for tokens longer
    than 3 characters, instead of exact-token queries (`"onion"`)
  - The exact query `"onion"` never matched `"Onions, raw"` because FTS5 tokenises
    that document as `onions` — a different token — so the correct result was
    invisible to the re-ranker entirely; the prefix query fixes this
  - Short tokens (≤ 3 chars) still use exact matching to avoid noisy expansions
    (e.g. `"of"*` matching `offal`, `official`, etc.)
  - Added `"onion"` + `"each"` (110 g) to `food_weights.json` so `1 onion`
    (no unit word) resolves correctly without a DB portion entry

## 0.1.16 — 2026-03-29

- Fixed FTS re-ranking bias against plural food names
  - `_rerank()` in `lookup.py` now strips one trailing `s` from the first
    food-name word before comparing to query words, so `"Onions, raw"` is
    correctly treated as a first-word match for the query `"onion"`
  - Both `"Onion dip"` and `"Onions, raw"` now land in priority group 0;
    BM25 order within the group picks the more relevant result
  - No regression for multi-word queries or non-plural names
  - Updated and added 2 tests in `tests/test_lookup.py` (202 total)

## 0.1.15 — 2026-03-29

- Implemented P9: Enhanced ingredient resolution (all four sub-tasks)
- **P9a: Food alias table** — maps abbreviations and synonyms to searchable food names
  - Bundled aliases in `ew/data/aliases.json`: `msg` → monosodium glutamate, `evoo` → olive oil, `ghee` → clarified butter, and 18 more
  - User alias table (`user_food_alias`) stored in `work/ew.db`; user entries take priority
  - Substitution applied as the final step of `_clean_food_query()` (exact match only)
  - `ew alias list` / `ew alias add KEY REPLACEMENT` management commands
  - During `recipe eval --interactive`, no-match items prompt for a better search term and save it
- **P9b: Food weight reference table** — per-food, per-unit gram estimates beyond the generic piece estimates
  - Bundled reference in `ew/data/food_weights.json`: 41 entries covering shallots, mushrooms, onions, eggs, common vegetables and fruits
  - User overrides in `work/food_weights.json`; user entries prepended (checked first)
  - Lookup in `resolve_grams()` between the portion DB and `_PIECE_GRAM_ESTIMATES`; word-prefix matching handles plurals
  - `ew weights list [food]` / `ew weights add FOOD UNIT GRAMS` management commands
- **P9c: Interactive resolution** — `ew recipe eval --interactive` (`-i`) flag
  - After initial pass, collects no-match items and 1 g fallbacks, then prompts once per item
  - No-match responses saved to `user_food_alias`; gram answers saved to `user_portion_cache` (DB table)
  - Resolved items re-run the full pipeline and update in-place before rendering
  - `ew portions list` / `ew portions clear` management commands
  - Non-interactive runs (no `-i`) are unaffected; piped output stays clean
- **P9d: To-taste defaults** — resolves unquantified seasoning lines instead of skipping them
  - Bundled defaults in `ew/data/taste_defaults.json`: salt (2 g), pepper (0.5 g), 20+ herbs and spices
  - When `parse_ingredient()` finds no quantity but the cleaned food text matches a default key, returns a `ParsedIngredient` with the default amount and a `"to-taste default, assumed Xg"` note
  - User overrides in `work/taste_defaults.json`
  - `ParsedIngredient` gains an optional `note` field; displayed in the recipe eval warning column
- New `ew/resolution.py` module; `ResolutionContext` dataclass bundles all four tables
- `ew/db.py` gains two new tables: `user_food_alias` and `user_portion_cache`
- `pyproject.toml` adds `package-data` to ship `ew/data/*.json`
- 42 new tests in `tests/test_resolution.py` (201 total)

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
