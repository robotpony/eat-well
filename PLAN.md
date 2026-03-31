# Implementation Plan


## Next features

### P6: Web UI

Browser-based form served directly by `ew serve`. No external server needed.

- `ew serve` launches a local HTTP server (`localhost:8080`); `--host`/`--port` flags
- Lookup form: text input → renders the P5 HTML label fragment inline
- Recipe form: multi-line textarea + servings → renders the P5 recipe breakdown inline
- Single static template (`ew/templates/index.html`); no JS framework

### P7: Service API

Run `ew` as a local HTTP service for programmatic access from other tools.

- Flask app in `ew/server.py`; added as an optional dependency (`ew[serve]`)
- JSON endpoints: `GET /lookup`, `POST /match`, `POST /recipe/eval`, `GET /sources`
- Content negotiation: `Accept: text/html` returns rendered fragment; `Accept: application/json` returns JSON
- `GET /` serves the P6 web UI
- Tests via Flask's test client

### P8: LLM ingredient matching

Fallback parser for lines the regex can't handle, improving real-world recipe coverage.

- `ew/llm.py` — `LLMProvider` Protocol with `extract_ingredient(text) -> dict | None`
- Built-in providers: `AnthropicProvider` (claude-haiku-4-5) and `OllamaProvider` (local, no API key)
- `--llm-provider anthropic|ollama|none` flag; default `none`
- Structured JSON response (`amount`, `unit`, `food`); validated before use
- Response cache in `work/llm_cache.sqlite` (7-day TTL) to avoid redundant API calls
- Used as fallback when `parse_ingredient()` returns `None`
- Tests via mock provider

### P9: Enhanced ingredient resolution *(done)*

Four sub-tasks sharing a common pattern: bundled defaults + user override layer in `work/`.

#### P9a: Food alias table *(done)*

Map abbreviations and common synonyms to searchable food names before FTS.

- Bundled aliases ship with the package (`ew/data/aliases.json`): `"msg"` → `"monosodium glutamate"`, `"e621"` → `"monosodium glutamate"`, `"evoo"` → `"olive oil"`, etc.
- User alias table stored in `work/ew.db` (`user_food_alias`): same schema, takes priority over bundled list
- Applied in `_clean_food_query()` as a final substitution step after noise stripping
- When `recipe eval` encounters a no-match, prompt the user: *"No result for 'X'. Enter a better search term (or blank to skip):"* — saves non-blank answers to `user_food_alias`
- `ew alias list` shows all aliases (bundled + user); `ew alias add MSG "monosodium glutamate"` adds one manually
- Tests: alias substitution, user alias priority over bundled, no-match prompt path

#### P9b: Food weight reference table *(done)*

Per-food, per-unit gram estimates that extend and supersede the generic `_PIECE_GRAM_ESTIMATES` table in `parser.py`.

- Bundled reference ships with the package (`ew/data/food_weights.json`): food key (substring match) + unit → grams + note
  - Examples: `shallot + each → 30g`, `mushroom + cup → 70g (sliced)`, `onion + medium → 110g`, `onion + cup → 160g (chopped)`, `spinach + cup → 30g`
- User overrides stored in `work/food_weights.json`; loaded and merged on startup, user entries win
- Lookup order in `resolve_grams()`: direct metric → food_portion DB → food weight reference (food-specific) → `_PIECE_GRAM_ESTIMATES` (unit-only) → 1g fallback
- Food key matching: exact then substring (`"sliced mushrooms"` → `"mushroom"` key matches)
- `ew weights list [food]` shows reference entries; `ew weights add "shallot" each 30` adds one manually
- Tests: exact match, substring match, user override, fallback chain

#### P9c: Interactive resolution *(done)*

Prompt the user during `recipe eval` when gram resolution falls back to 1g, so estimates improve over time.

- Opt-in via `--interactive` / `-i` flag on `ew recipe eval`
- After initial parse pass, collect all lines that used the 1g fallback or had no food match
- For each, prompt: *"'1 shallot' resolved to 1g. Enter weight in grams [skip]:"*
- Valid answers are cached to `work/user_portions.json` keyed by `(food_query, unit)` — used by `resolve_grams()` on subsequent runs before the 1g fallback
- Non-interactive runs (no `-i`) are silent; piped output and CI are unaffected
- `ew portions list` shows cached answers; `ew portions clear` removes them
- Tests: cache write, cache read on next call, silent mode when flag absent

#### P9d: "To taste" defaults *(done)*

Resolve unquantified seasoning lines (e.g., `salt, pepper (to taste)`) to a reasonable default rather than skipping.

- Bundled defaults table (`ew/data/taste_defaults.json`): maps food name patterns to a default amount + unit
  - `salt → 2g`, `pepper → 0.5g`, `spice / seasoning (generic) → 0.5g`
- When `parse_ingredient()` returns `None` and the food text matches a known to-taste item, emit a `ParsedIngredient` with the default amount and a `"to-taste default, assumed Xg"` note
- Scaled by `--servings N` when specified (the default is per-serving; 2 servings → 2× the default)
- User can override defaults in `work/taste_defaults.json`
- Matching is conservative: requires a food key match; ambiguous lines (no recognisable food name) still return `None`
- Tests: salt default, pepper default, servings scaling, unrecognised line still returns None

---

## Deferred

- Cross-source food deduplication (e.g., "almonds" across CNF / USDA Foundation / SR Legacy)
- User recipe repository (Google Docs integration)
- Fridge/pantry tracking
- Glycemic index data (not in CNF or USDA FDC; requires a separate source)
- iOS/macOS native UI
- CNF update/delta file processing
