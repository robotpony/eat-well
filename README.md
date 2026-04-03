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

Any dataset not found under `import/` is skipped with a notice. Safe to re-run.

## Lookup

```bash
ew lookup "raw almonds"
```

Shows the top matches and prompts you to pick one if there are multiple results. Displays a two-column nutrition label: per 100 g and per the first listed portion.

```bash
ew lookup "whole milk" --per 250              # second column: per 250 g
ew lookup "lait entier" --lang fr             # search and display in French (CNF foods)
ew lookup "almonds" --pick 2                  # skip the prompt, auto-select match 2
ew lookup "raw almonds" --format md           # output as a GFM markdown table
ew lookup "raw almonds" --format html         # output as a styled HTML document
ew lookup "raw almonds" --format html --output label.html   # write to file
```

Example output (truncated):

```
$ ew lookup "dark chocolate 70" --pick 1

Chocolate, dark, 70-85% cacao solids  USDA FoodData Central — SR Legacy

                                  per 100 g  1 undetermined (28.35 g)

Energy
  Energy                           598 kcal                  170 kcal
  Energy                           2,504 kJ                   710 kJ

Macros
  Protein                            7.79 g                   2.21 g
  Total lipid (fat)                  42.6 g                   12.1 g
  Fatty acids, total saturated       24.5 g                   6.94 g
  Carbohydrate, by summation         45.9 g                   13.0 g
  Fiber, total dietary               10.9 g                   3.09 g
  Sugars, Total                      24.0 g                   6.80 g

Minerals
  Sodium, Na                        20.0 mg                  5.67 mg
  Potassium, K                       715 mg                   203 mg
  Iron, Fe                          11.9 mg                  3.37 mg
  Magnesium, Mg                      228 mg                  64.6 mg
  …
```

## Match and recipe eval

```bash
ew match "1 cup whole milk"      # parse, find best match, show scaled label
ew match "100g almonds"
```

```bash
ew recipe eval ingredients.txt                     # aggregate nutrition across a recipe
ew recipe eval - < ingredients.txt                 # read from stdin
ew recipe eval breakfast.txt --servings 4          # per-serving column (total weight ÷ 4)
ew recipe eval ingredients.txt --portion 200       # per-portion column at a fixed 200 g
ew recipe eval ingredients.txt --interactive       # prompt to resolve unmatched items; saves answers
ew recipe eval ingredients.txt --format md         # output as markdown tables
ew recipe eval ingredients.txt --format html --output recipe.html
```

The totals table always shows two columns: the recipe total (labelled with the total gram weight, e.g. `Total (2,056 g)`) and a per-portion column. The per-portion column defaults to 150 g (`Per 150 g`). `--servings N` divides the total recipe weight by N to show a realistic per-serving amount (e.g. `Per serving (÷4, 514 g)`). `--portion GRAMS` sets the gram weight directly.

Ingredient file format — one per line:

```
1 cup rolled oats
2 large eggs
1 tbsp olive oil
# comments and blank lines are ignored
```

Each line is parsed for a leading quantity and optional unit, then matched to the best FTS result. Matched lines show grams resolved; unmatched lines are flagged. Supported units include `g`, `kg`, `oz`, `lb`, `cup`, `tbsp`, `tsp`, `ml`, `l`, plus piece units (`large`, `medium`, `small`, `slice`, `clove`, etc.).

The parser also handles:
- **Amounts buried in parentheses**: `garlic powder (½ teaspoon)` → 0.5 tsp garlic powder
- **To-taste defaults**: `salt, pepper (to taste)` → resolved using a bundled default (2 g salt) rather than skipped
- **Food aliases**: `1 tsp msg` or `2 tsp Accent MSG` → searches for "monosodium glutamate"; aliases match any word in the ingredient name, not just the full text; add your own with `ew alias add`

## Resolution management

These commands manage the lookup tables that fill in missing weights and names during recipe eval.

```bash
ew alias list                              # show bundled + user aliases (abbreviations → food names)
ew alias add MSG "monosodium glutamate"   # add a user alias
```

```bash
ew weights list                            # show food weight reference (piece/cup weights per food)
ew weights list mushroom                   # filter by food name
ew weights add shallot each 30            # add a custom gram weight
```

The food weight reference covers common items where the DB portion data is missing or imprecise — shallots, onions, mushrooms by the cup, eggs, and so on. User entries are checked before the bundled defaults.

```bash
ew portions list                           # show gram answers saved during --interactive sessions
ew portions clear                          # clear the cache
```

## Development

```bash
pytest tests/
```

212 tests, all in-memory — no data files required. See `ARCHITECTURE.md` for schema details and `PLAN.md` for the roadmap.
