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
ew lookup "whole milk" --per 250        # second column: per 250 g
ew lookup "lait entier" --lang fr       # search and display in French (CNF foods)
ew lookup "almonds" --pick 2            # skip the prompt, auto-select match 2
ew lookup "raw almonds" --format md     # output as a GFM markdown table
```

Example output (truncated):

```
$ ew lookup "dark chocolate"

  1  Chocolate, dark, 70-85% cacao solids  USDA SR Legacy
  2  Chocolate, dark, 45-59% cacao solids  USDA SR Legacy
  3  Chocolate syrup, dark                 USDA SR Legacy

Pick [1-3]: 1

Chocolate, dark, 70-85% cacao solids  USDA SR Legacy

                                per 100 g  1 bar (28 g)

Energy
  Energy (kcal)                   598 kcal     167 kcal
  Energy (kJ)                   2,502 kJ        700 kJ

Macros
  Protein                         7.79 g        2.18 g
  Total fat                       42.6 g         11.9 g
  Saturated fat                   24.5 g          6.9 g
  Carbohydrate                    45.9 g         12.9 g
  Dietary fibre                   10.9 g          3.1 g
  Sugars                          24.2 g          6.8 g

Minerals
  Sodium                          20.0 mg         5.6 mg
  Potassium                       715  mg          200 mg
  Iron                            11.90 mg         3.33 mg
  Magnesium                       228 mg           64 mg
  …
```

## Match and recipe eval

```bash
ew match "1 cup whole milk"      # parse, find best match, show scaled label
ew match "100g almonds"
```

```bash
ew recipe eval ingredients.txt           # aggregate nutrition across a recipe
ew recipe eval - < ingredients.txt
ew recipe eval breakfast.txt --servings 2
ew recipe eval ingredients.txt --format md   # output as markdown tables
```

Ingredient file format — one per line:

```
1 cup rolled oats
2 large eggs
1 tbsp olive oil
# comments and blank lines are ignored
```

Each line is parsed for a leading quantity and optional unit, then matched to the best FTS result. Matched lines show grams resolved; unmatched lines are flagged. Supported units include `g`, `kg`, `oz`, `lb`, `cup`, `tbsp`, `tsp`, `ml`, `l`, plus piece units (`large`, `medium`, `small`, `slice`, `clove`, etc.).

## Development

```bash
pytest tests/
```

105 tests, all in-memory — no data files required. See `ARCHITECTURE.md` for schema details and `PLAN.md` for the roadmap.
