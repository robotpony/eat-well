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
| P1 | CLI lookup tool (`ew lookup`) | Planned |
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

## Development

```bash
pytest tests/
```

26 tests covering schema creation, CNF and USDA import, nutrient deduplication, portion calculations, and FTS indexing. No large data files required — tests use small in-memory fixtures.

See `ARCHITECTURE.md` for the database schema and import pipeline design, and `PLAN.md` for the phased roadmap.
