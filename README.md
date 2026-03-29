# Eat Well + Win The Fridge

Nutrition lookup and recipe planning. Searches the Canadian Food Nutrient Database (CNF) and USDA FoodData Central.

## Setup

```bash
./setup
source .venv/bin/activate
```

Requires Python 3.11+. See `import/README.md` for downloading the data files.

## Importing data

```bash
ew import           # reads import/ and writes work/ew.db
ew sources          # verify what loaded
```

Any dataset not found under `import/` is skipped with a notice. Safe to re-run. See `ew import --help` for path overrides and environment variable options.

## Lookup

```bash
ew lookup "raw almonds"
```

Shows the top matches and prompts you to pick one if there are multiple results. Displays a two-column nutrition label: per 100 g and per the first listed portion.

```bash
ew lookup "whole milk" --per 250     # second column: per 250 g
ew lookup "lait entier" --lang fr    # search and display in French (CNF foods)
ew lookup "almonds" --pick 2         # skip the prompt, auto-select match 2
```

## Development

```bash
pytest tests/
```

44 tests, all in-memory — no data files required. See `ARCHITECTURE.md` for schema details and `PLAN.md` for the roadmap.
