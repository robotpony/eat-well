# Import Data

Raw nutrition data for `ew import`. Neither directory is checked into git — you need to download the source files yourself.

## Directory structure

```
import/
  cad/
    cnf-fcen-csv/               ← unzip the CNF CSV download here
  usa/
    FoodData_Central_foundation_food_csv_2023-04-20/   ← extracted
    FoodData_Central_sr_legacy_food_csv_2018-04.zip    ← keep zipped
    FoodData_Central_survey_food_csv_2022-10-28.zip    ← keep zipped
```

## Canadian data (CNF)

Download the **Canadian Nutrient File 2015 — CSV** from Health Canada. Extract the zip so that `FOOD NAME.csv`, `NUTRIENT AMOUNT.csv`, etc. are directly inside `import/cad/cnf-fcen-csv/`.

Key files used by the importer:

| File | Contents |
|---|---|
| `FOOD NAME.csv` | Food descriptions (English and French) |
| `FOOD GROUP.csv` | Food group categories |
| `NUTRIENT NAME.csv` | Nutrient names, symbols, units |
| `NUTRIENT AMOUNT.csv` | Per-100g nutrient values |
| `MEASURE NAME.csv` | Portion measure descriptions |
| `CONVERSION FACTOR.csv` | Measure → gram weight conversions |

## US data (USDA FoodData Central)

Download from the USDA FoodData Central download page. Three datasets are required:

| Dataset | Format | Path |
|---|---|---|
| Foundation Foods | CSV (extract) | `import/usa/FoodData_Central_foundation_food_csv_2023-04-20/` |
| SR Legacy | ZIP (keep zipped) | `import/usa/FoodData_Central_sr_legacy_food_csv_2018-04.zip` |
| Survey Foods / FNDDS | ZIP (keep zipped) | `import/usa/FoodData_Central_survey_food_csv_2022-10-28.zip` |

The importer reads SR Legacy and Survey directly from their zip files — no extraction needed.

## Running the import

```bash
ew import
```

Any source whose directory or zip is not found is skipped with a notice. Safe to re-run.

See the project README for override options and environment variables.
