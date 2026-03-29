# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Eat Well + Win The Fridge (EW-WTF)** is a nutrition and recipe planning tool. The goal is accurate nutrition lookups and recipe suggestions using existing ingredients and dietary objectives.

## Development Phases

- **P0 (current)**: Import public nutrition data into a DB schema
- **P1**: CLI tool for nutrition lookups (e.g., `ew lookup "raw almonds"`) with markdown output
- **P2**: Query tools
- **P3**: Markdown generation from queries

No application code exists yet. The repo contains raw nutrition data files only.

## Data Sources

Raw nutrition data lives in `import/`:

- `import/cad/` — Canadian Food Nutrient Database (CNF-FCEN), CSV and Excel formats, with separate update/change files
- `import/usa/` — USDA FoodData Central (2023-04-20 release), CSV and JSON formats

**US data is large** (3.3 GB uncompressed). Several datasets are zipped. Key files:
- `foundationDownload.json` — foundation foods (whole/minimally processed)
- `brandedDownload.json` — branded/packaged products
- `FoodData_Central_foundation_food_csv_2023-04-20/` — CSV versions of foundation data

## Build, Test, and Lint Commands

None configured yet. Add them here as the project is set up.

## Architecture and Plan

See `ARCHITECTURE.md` for the full schema, import pipeline design, and library choices. See `PLAN.md` for the phased implementation breakdown.

## Architecture Notes

The planned data model needs to unify two distinct schemas:

**CNF (Canada)**: Tables include `FOOD NAME`, `NUTRIENT AMOUNT`, `CONVERSION FACTOR`, `FOOD GROUP`, `REFUSE AMOUNT`, `YIELD AMOUNT`, `MEASURE NAME`, `SOURCE`. Relationships are via numeric food/nutrient codes.

**FoodData Central (USA)**: Normalized CSV tables — `food`, `nutrient`, `food_nutrient`, `food_portion`, `food_attribute`, `branded_food`, and others. JSON equivalents available for foundation and branded sets.

Key design decisions to make before writing import code:
1. Whether to merge both databases into a single schema or keep them as separate sources with a unified query layer
2. Canonical nutrient identifiers (CNF uses its own codes; USDA uses FDC IDs and nutrient numbers)
3. Unit normalization (both use per-100g as base, but branded foods vary)
