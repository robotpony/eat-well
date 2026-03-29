# Changelog

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
