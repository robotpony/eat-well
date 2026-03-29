# Implementation Plan

## Quality improvements (from recipe output review)

Issues identified by running both example recipes and reviewing output.

### 1. Table column collapse *(done)*

The `input` column is `no_wrap=True`, which on long ingredient lines claims most
of the terminal width and squeezes match names and notes to ~3 visible characters.
Fix: allow the input column to wrap/truncate; constrain the note column to a
fixed max width.

### 2. Preparation adjectives stripped from food query *(done)*

`4 cups of sliced mushrooms` → food_query `sliced mushrooms` → FTS requires
"sliced" AND "mushrooms" → no match. Common leading prep adjectives (`sliced`,
`diced`, `chopped`, `minced`, `fresh`, `dried`, `cooked`, `raw`) should be
stripped just as comma-descriptors after the noun already are.

### 3. Inline slash alternative without spaces *(done)*

`50g lemon/lime juice` → food_query `lemon/lime juice`. `_NOTE_PATTERNS` only
strips ` / annotation` (with surrounding spaces). After `_build_fts_query`
removes the `/`, FTS searches `"lemon" AND "lime" AND "juice"` — no single food
has all three → no match. Should strip `/alternative` (no surrounding spaces)
leaving `lemon juice`.

### 4. Wrong top FTS match for short queries *(done)*

`avocado` → "Oil, avocado"; `onion` → "Bread, onion". BM25 ranks long compound
names above short exact matches. A post-FTS re-ranking step penalising food
names much longer than the query would fix both cases.

Fixed by fetching a wider FTS candidate pool (4× limit, min 20) and stable-sorting
by whether the food name's first component matches a query word. BM25 order is
preserved as a tiebreaker within each group.

### 5. Piece-unit 1g fallback underestimates common ingredients *(done)*

`1 shallot` and `4 cloves garlic` fall back to 1g/item because the DB has no
portion data for them. A built-in weight table (shallot ≈ 30g, garlic clove ≈
6g, egg ≈ 50g, etc.) as a second fallback before the 1g last resort would
significantly improve totals accuracy.

Fixed by adding `_PIECE_GRAM_ESTIMATES` in `parser.py` covering cloves, heads,
sprigs, bunches, stalks, ears, strips, and leaves. Used as a fallback after the
food_portion lookup fails, with an "estimated N g each" warning.

### 6. Amount buried in parentheses *(done)*

`garlic powder (½ teaspoon)` → parser returns None (no leading number).

Fixed by `_PAREN_AMOUNT_RE` in `parser.py`: when no leading number is found,
the regex scans for `food name (amount unit)` and extracts the buried amount.
Unicode fractions are normalised before matching. Lines with non-numeric
parentheticals (`to taste`, `big pinch`) continue to return None.

---

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

---

## Deferred

- Cross-source food deduplication (e.g., "almonds" across CNF / USDA Foundation / SR Legacy)
- User recipe repository (Google Docs integration)
- Fridge/pantry tracking
- Glycemic index data (not in CNF or USDA FDC; requires a separate source)
- iOS/macOS native UI
- CNF update/delta file processing
