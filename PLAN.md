# Implementation Plan

## ~~P0: Schema and data import~~ ✓

Goal: a populated `ew.db` with all three US datasets and CNF.

### 0.1 Project structure

```
eat-well/
    ew/
        __init__.py
        db.py           -- connection, schema creation, migrations
        importers/
            __init__.py
            base.py
            cnf.py
            usda_foundation.py
            usda_sr_legacy.py
            usda_survey.py
    tests/
        test_import.py
    pyproject.toml
    ew.db               -- generated, gitignored
```

### 0.2 Schema setup

- `db.py` creates all tables and FTS index on first run
- Schema versioned via a `schema_version` table; migrations run automatically
- `ew import` drops and recreates all data tables (idempotent re-import)

### 0.3 Importers (in order)

Each importer logs row counts and errors. Any row that fails validation is skipped with a warning, not a crash.

1. **CNF** (`import/cad/cnf-fcen-csv/`)
   - Sources: FOOD NAME, FOOD GROUP, NUTRIENT NAME, NUTRIENT AMOUNT, CONVERSION FACTOR, MEASURE NAME
   - Skips: update/change files (delta format; treat baseline as authoritative for now)
   - French names: stored in `name_fr` columns on `nutrient`, `food`, `food_category`, `food_portion`

2. **USDA Foundation** (`import/usa/FoodData_Central_foundation_food_csv_2023-04-20/`)
   - Sources: `food.csv`, `nutrient.csv`, `food_nutrient.csv`, `food_portion.csv`, `food_category` (inferred from food)
   - Skips: `acquisition_samples`, `agricultural_samples`, `sub_sample_result`, lab methods (analytical metadata, not needed for lookups)

3. **USDA SR Legacy** (unzip `FoodData_Central_sr_legacy_food_csv_2018-04.zip` first)
   - Same CSV structure as foundation
   - ~8,800 foods; good broad coverage for common ingredients

4. **USDA Survey / FNDDS** (unzip `FoodData_Central_survey_food_csv_2022-10-28.zip`)
   - Includes combination dishes useful for recipe evaluation later
   - Same import path as foundation/SR

### 0.4 FTS rebuild

After all importers complete, drop and rebuild `food_fts`. This is separate from per-importer inserts so FTS stays consistent.

### 0.5 Validation ✓

26 unit tests cover: schema creation, CNF import, USDA import, nutrient
deduplication, gram-weight calculation, FTS rebuild, missing-file handling.

Run: `pytest tests/`

---

## ~~P1: CLI lookup tool~~ ✓

Goal: `ew lookup "raw almonds"` returns a readable nutrition label.

### 1.1 FTS search

- Match against `food_fts` using FTS5 BM25 ranking
- Return top 5 matches with source label
- If multiple results, prompt user to pick one (or accept `--pick N` flag)

### 1.2 Nutrition label formatter

Display order follows `nutrient.rank`. Group into sections:

1. Energy (kcal, kJ)
2. Macros (fat, carbs, fibre, sugars, protein)
3. Minerals (sodium, potassium, calcium, iron, etc.)
4. Vitamins (A, B-group, C, D, E, K)

Use `rich` tables. Support `--per <amount>g` to scale values (default: per 100g and per first listed portion).

### 1.3 Language support

`--lang fr` switches search and output to French. Only affects CNF foods (USDA has no French data).

### 1.4 `ew sources` command

Lists loaded sources, version, and row counts. Quick sanity check.

---

## P2: Query tools

Goal: evaluate recipes and compare ingredients.

### 2.1 Ingredient matching

`ew match "1 cup whole milk"` — parse a quantity + ingredient string, find best food match, return scaled nutrients.

Parsing strategy: extract amount + unit first (regex), then fuzzy-search the remainder.

### 2.2 Recipe evaluation

Accept a simple ingredient list (one per line, `amount unit ingredient`):

```
ew recipe eval ingredients.txt
```

Output: aggregate nutrition totals + per-portion breakdown (if `--servings N` given).

### 2.3 Portion math

- Convert any listed measure to grams using `food_portion`
- Fall back to gram_weight of 1g if no matching portion found (with a warning)

---

## P3: Markdown generation

Goal: produce formatted output suitable for notes, docs, or a future web view.

### 3.1 `ew lookup --format md`

Nutrition label as a markdown table. Useful for Obsidian, GitHub, or recipe docs.

### 3.2 `ew recipe eval --format md`

Full recipe nutrition breakdown as markdown.

---

## Deferred

These are out of scope until P3 is complete:

- Cross-source food deduplication (e.g., "almonds" in CNF vs. USDA foundation vs. SR legacy)
- User recipe repository (Google Docs integration)
- Fridge/pantry tracking
- Glycemic index data (not in CNF or USDA FDC; requires a separate source)
- iOS/macOS native UI
- CNF update/delta file processing
