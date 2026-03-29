# Eat Well + Win The Fridge

A tool for learning about food and planning what to eat.

1. Clear, accurate nutrition information — macros, micros, glycemic absorption, protein/fat completeness scores.
2. Recipe suggestions and evaluation using existing ingredients and dietary objectives.

## Features

- Quick lookup of individual ingredients
- Recipe evaluation with per-portion nutrition breakdowns
- Scale recipes up and down, or convert to ratios for comparison
- Classify recipes (low-carb, low-cal, authentic, etc.)
- Track fridge/pantry inventory
- Smart dietary objective capture and suggestions

## Status

| Phase | Description | Status |
|---|---|---|
| P0 | Data import and schema | ✓ Done |
| P1 | CLI lookup tool (`ew lookup`) | ✓ Done |
| P2 | Query tools (`ew match`, `ew recipe eval`) | Planned |
| P3 | Markdown output | Planned |

## Setup

Requires Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

After activating the venv, the `ew` command is available.

## Getting the data

The importer expects this structure under `import/`:

```
import/
  cad/
    cnf-fcen-csv/               ← unzip the CNF CSV download here
  usa/
    FoodData_Central_foundation_food_csv_2023-04-20/   ← extracted
    FoodData_Central_sr_legacy_food_csv_2018-04.zip    ← keep zipped
    FoodData_Central_survey_food_csv_2022-10-28.zip    ← keep zipped
```

**Canadian data (CNF):** Download the "Canadian Nutrient File 2015 — CSV" from Health Canada. Extract the zip so that `FOOD NAME.csv`, `NUTRIENT AMOUNT.csv`, etc. are directly inside `import/cad/cnf-fcen-csv/`.

**US data (USDA FoodData Central):** Download from the USDA FoodData Central download page. You need three datasets:

- Foundation Foods CSV (extract to `import/usa/`)
- SR Legacy CSV (leave as zip in `import/usa/`)
- Survey Foods / FNDDS CSV (leave as zip in `import/usa/`)

The importer reads the SR Legacy and Survey datasets directly from their zip files — no extraction needed.

## Importing

```bash
ew import
```

Reads all available sources from `import/` and writes `work/ew.db`. Any source whose directory or zip isn't found is skipped with a notice. Safe to re-run.

```bash
ew sources          # list loaded sources and food counts
ew import --help    # path overrides and options
```

Override default paths:

```bash
EW_DB=/path/to/nutrition.db EW_IMPORT_DIR=/path/to/data ew import
```

The database is written to `work/ew.db` by default. The `work/` directory is created automatically and is git-ignored.

## Lookup

```bash
ew lookup "raw almonds"
```

Shows the top matches. If there is more than one, you will be prompted to pick. Displays a two-column nutrition label: per 100 g and per the first listed portion.

```bash
ew lookup "whole milk" --per 250   # second column: per 250 g
ew lookup "lait entier" --lang fr  # search and display in French
ew lookup "almonds" --pick 2       # auto-select match 2
```

## Development

```bash
pytest tests/
```

44 tests covering schema creation, CNF and USDA import, nutrient deduplication, portion calculations, FTS indexing, and lookup/label rendering. No large data files required — tests use small in-memory fixtures.

See `ARCHITECTURE.md` for the database schema and import pipeline design, and `PLAN.md` for the phased roadmap.
