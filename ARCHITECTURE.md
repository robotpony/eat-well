# Architecture

## Overview

EW-WTF is a Python + SQLite application. The database is the core artifact — everything else (CLI, eventually iOS/macOS) is a query layer on top of it.

Data flows in one direction during import: raw CSVs → normalized schema → SQLite. Queries flow back out through the CLI and eventually a native UI.

```
import/
  cad/        ──┐
  usa/        ──┼──▶  importers/  ──▶  ew.db  ──▶  CLI (ew)
                │                               └──▶  iOS/macOS app (future)
  (future:      │
  user recipes)─┘
```

## Database Schema

All nutrient amounts are stored **per 100g**. Portion sizes store their gram weight, so any serving size can be computed as `(gram_weight / 100) * amount`.

### Core tables

```sql
-- Data source registry
CREATE TABLE source (
    id      INTEGER PRIMARY KEY,
    code    TEXT NOT NULL UNIQUE,  -- 'cnf', 'usda_foundation', 'usda_sr_legacy', 'usda_survey'
    name    TEXT NOT NULL,
    version TEXT                   -- e.g., '2015', '2023-04-20'
);

-- Canonical nutrients (shared across all sources)
-- Key insight: CNF NutrientCode == USDA nutrient_nbr (both use the USDA SR numbering system)
CREATE TABLE nutrient (
    id       INTEGER PRIMARY KEY,
    sr_nbr   INTEGER UNIQUE NOT NULL,  -- USDA SR number = CNF NutrientCode
    symbol   TEXT,                     -- e.g., 'PROT', 'FAT', 'CHOCDF'
    name_en  TEXT NOT NULL,
    name_fr  TEXT,                     -- from CNF
    unit     TEXT NOT NULL,            -- 'g', 'mg', 'µg', 'kcal', 'kJ', 'IU'
    rank     INTEGER                   -- display order for nutrition labels
);

-- Food categories (both sources have groupings; stored unified)
CREATE TABLE food_category (
    id         INTEGER PRIMARY KEY,
    source_id  INTEGER NOT NULL REFERENCES source(id),
    source_key TEXT NOT NULL,          -- original ID or code from source
    name_en    TEXT NOT NULL,
    name_fr    TEXT                    -- CNF only
);

-- Foods (one row per food per source; no cross-source deduplication yet)
CREATE TABLE food (
    id             INTEGER PRIMARY KEY,
    source_id      INTEGER NOT NULL REFERENCES source(id),
    source_food_id TEXT    NOT NULL,   -- FoodID (CNF) or fdc_id (USDA)
    name_en        TEXT    NOT NULL,
    name_fr        TEXT,               -- CNF only
    scientific_name TEXT,              -- CNF only
    category_id    INTEGER REFERENCES food_category(id),
    UNIQUE (source_id, source_food_id)
);

-- Nutrient values (main fact table)
CREATE TABLE food_nutrient (
    id           INTEGER PRIMARY KEY,
    food_id      INTEGER NOT NULL REFERENCES food(id),
    nutrient_id  INTEGER NOT NULL REFERENCES nutrient(id),
    amount       REAL    NOT NULL,     -- per 100g
    std_error    REAL,
    n_obs        INTEGER,
    UNIQUE (food_id, nutrient_id)
);

-- Portions and serving sizes
-- CNF: gram_weight = ConversionFactorValue * 100
-- USDA: gram_weight stored directly in food_portion.gram_weight
CREATE TABLE food_portion (
    id           INTEGER PRIMARY KEY,
    food_id      INTEGER NOT NULL REFERENCES food(id),
    measure_en   TEXT    NOT NULL,     -- e.g., '1 cup', '1 medium apple'
    measure_fr   TEXT,                 -- CNF only
    gram_weight  REAL    NOT NULL,
    seq_num      INTEGER               -- display order
);
```

### Supporting tables (import only)

These are populated during import but not queried at runtime:

- `food_refuse` — inedible portion by weight (CNF: REFUSE AMOUNT). Used to adjust gram weights for whole foods (e.g., banana with peel).
- `food_yield` — cooking weight change factor (CNF: YIELD AMOUNT). Tracks how raw-to-cooked weight ratios affect nutrient density.

### User resolution tables (P9)

These tables live in `work/ew.db` alongside the main data and accumulate over time as the user resolves unknowns.

```sql
-- User-defined food name aliases, e.g. "msg" → "monosodium glutamate".
-- Merged with bundled aliases from ew/data/aliases.json; user entries win on conflict.
CREATE TABLE user_food_alias (
    id          INTEGER PRIMARY KEY,
    input_key   TEXT NOT NULL UNIQUE,   -- normalised lower-case query fragment
    replacement TEXT NOT NULL,          -- substitute search term
    created_at  TEXT NOT NULL           -- ISO-8601 timestamp
);

-- User-cached gram resolutions from interactive recipe eval sessions.
-- Keyed by (food_query, unit); consulted by resolve_grams() before the 1g fallback.
CREATE TABLE user_portion_cache (
    id          INTEGER PRIMARY KEY,
    food_query  TEXT NOT NULL,
    unit        TEXT,                   -- NULL for unitless (piece counts)
    gram_weight REAL NOT NULL,
    created_at  TEXT NOT NULL,
    UNIQUE (food_query, unit)
);
```

### FTS index (full-text search)

```sql
CREATE VIRTUAL TABLE food_fts USING fts5(
    name_en,
    name_fr,
    content=food,
    content_rowid=id
);
```

Populated after import. Powers `ew lookup "raw almonds"` with ranking by relevance.

### Bundled reference data (P9)

Static JSON files shipped inside the package under `ew/data/`. Read once at startup and merged with any user overrides from `work/`.

| File | Purpose |
|---|---|
| `ew/data/aliases.json` | Food name aliases: `{"msg": "monosodium glutamate", "evoo": "olive oil", …}` |
| `ew/data/food_weights.json` | Per-food gram estimates: `[{"key": "shallot", "unit": "each", "grams": 30}, …]` |
| `ew/data/taste_defaults.json` | To-taste defaults: `[{"key": "salt", "grams": 2, "unit": "g"}, …]` |

User overrides follow the same schema and live in `work/`. They are merged at load time; user entries always win.

## Ingredient Resolution Pipeline (P2 / P9)

The full resolution pipeline for a single ingredient line, in order:

```
raw text
  │
  ├─ unicode normalisation (½ → 1/2)
  ├─ compact-unit match  ("100g almonds")
  ├─ leading-amount match  ("2 cups flour")
  │     └─ parenthetical-amount fallback  ("garlic powder (½ tsp)")
  │
  ├─ _clean_food_query()
  │     ├─ strip alt-amount prefix  ("/3 lbs")
  │     ├─ strip "of " preposition
  │     ├─ strip parentheticals and slash/or notes
  │     ├─ strip comma descriptor
  │     ├─ strip prep adjectives  (sliced, diced, …)
  │     └─ alias substitution  ("msg" → "monosodium glutamate")   ← P9a
  │
  ├─ to-taste default lookup  (salt → 2g when no amount found)    ← P9d
  │
  └─ FTS search → _rerank() → best match
        │
        └─ resolve_grams()
              ├─ direct metric table  (g, kg, ml, …)
              ├─ food_portion DB lookup
              ├─ user portion cache                                ← P9c
              ├─ food weight reference  (food + unit)             ← P9b
              ├─ _PIECE_GRAM_ESTIMATES  (unit-only)
              └─ 1g fallback  (+interactive prompt when -i)       ← P9c
```

## Import Pipeline

Each source has its own importer module. All importers share a common interface:

```
ew/importers/
    base.py           -- shared helpers (bulk insert, progress, nutrient mapping)
    cnf.py            -- Canadian Food Nutrient Database
    usda_foundation.py
    usda_sr_legacy.py
    usda_survey.py
```

Import order matters due to foreign keys:
1. `source` rows
2. `nutrient` (deduplicated via sr_nbr; CNF runs first to capture French names)
3. `food_category`
4. `food`
5. `food_nutrient`
6. `food_portion`
7. Rebuild FTS index

### Nutrient deduplication

CNF and USDA share the same nutrient numbering system (both derive from USDA SR). A nutrient is inserted once keyed on `sr_nbr`. When CNF runs first, it populates `name_fr`. USDA rows update `name_en` if it's more precise (USDA names tend to be more specific, e.g., "Carbohydrate, by difference" vs. CNF's "CARBOHYDRATE, TOTAL (BY DIFFERENCE)").

Nutrients unique to one source (e.g., USDA's Atwater-specific energy factors, CNF's oxalic acid) are inserted with a null on the other source's fields.

### CNF conversion factors → gram weights

CNF stores a `ConversionFactorValue` that is a multiplier relative to 100g:

```
gram_weight = ConversionFactorValue * 100
```

This converts naturally to the `food_portion.gram_weight` format used by USDA.

## CLI Design (P1)

The `ew` command is implemented with [Click](https://click.palletsprojects.com/). Database path resolves to `~/.local/share/eat-well/ew.db` by default, overridable via `EW_DB` environment variable.

```
ew lookup "raw almonds"          # fuzzy search + nutrition label
ew lookup --lang fr "amandes"    # French search
ew sources                       # list loaded data sources and row counts
ew import                        # (re)run all importers
```

Nutrition label output follows the standard label order (energy → fat → carbs → protein → fibre → vitamins/minerals), sorted by `nutrient.rank`.

## Libraries

| Library | Purpose | Why |
|---|---|---|
| `click` | CLI framework | Clean argument parsing, help generation, composable commands |
| `sqlite3` | Database (stdlib) | No extra deps; SQLite is sufficient for read-heavy local queries |
| `csv` | CSV parsing (stdlib) | All import files are standard CSV; no need for pandas |
| `rich` | Terminal output | Tables and formatted nutrition labels without manual ANSI |

No ORM. Raw SQL with named parameters keeps the import fast and the queries readable.

## Future: iOS/macOS Integration

The SQLite database is the integration point. The native app ships with a pre-built `ew.db` (or downloads it) and queries it directly via GRDB or SQLite.swift. No server required.

The schema is intentionally flat and denormalization-friendly — the `food_fts` table and direct foreign key lookups are fast enough for on-device use.
