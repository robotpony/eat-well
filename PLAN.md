# Implementation Plan

## ~~P4: Markdown generation~~ ✓

Goal: produce formatted output suitable for notes, docs, or a future web view.

### 4.1 `ew lookup --format md` ✓

Nutrition label as a GFM table with section headers and two-column layout.

### 4.2 `ew recipe eval --format md` ✓

Full recipe breakdown: ingredient match table + nutrient totals table, with
optional per-serving column.

---

## P5: HTML output

Goal: export nutrition labels and recipe summaries as styled HTML files.

### 5.1 `--format html` flag

Add `--format html` to `ew lookup` and `ew recipe eval`. When set, output is an
HTML document instead of rich console output.

### 5.2 HTML renderer

New `ew/html.py` module with:
- `render_label_html(nutrients, food_name, per_g, portion)` — nutrition label table
- `render_recipe_html(results, title, servings)` — full recipe breakdown
- Inline CSS only; no external dependencies or frameworks
- Visual parity with the rich console layout (sections, two-column label)

### 5.3 `--output FILE` flag

Write HTML to a file instead of stdout. Default behaviour (no flag) prints to
stdout so it can be piped.

### 5.4 Validation

Unit tests in `tests/test_html.py` covering:
- Label and recipe renderers produce valid HTML fragments
- Section grouping matches `lookup.SECTIONS` order
- `--output` writes the file and the file is non-empty

---

## P6: Web UI

Goal: browser-based form for interactive lookups and recipe evaluation, served
directly by the `ew` tool.

### 6.1 `ew serve` command

Launches a local HTTP server (default `localhost:8080`). Flags: `--host`, `--port`.

### 6.2 Lookup form

Single-page form: text input → `GET /lookup?q=…` → returns the P5 HTML label
fragment embedded in the page.

### 6.3 Recipe form

Multi-line textarea + servings field → `POST /recipe/eval` → returns the P5
HTML recipe breakdown embedded in the page.

### 6.4 Static template

Single HTML template (`ew/templates/index.html`). Uses the P5 HTML output as
the response body fragment; no JS framework required.

---

## P7: Service API

Goal: run `ew` as a local HTTP service so other applications can query it
programmatically via JSON.

### 7.1 Flask application

New `ew/server.py` using Flask. `ew serve` (from P6) launches this app.
Flask added as an optional dependency (`ew[serve]`).

### 7.2 JSON endpoints

| Method | Path | Body / Params | Returns |
|--------|------|---------------|---------|
| `GET` | `/lookup` | `?q=raw+almonds&pick=1` | food + nutrient rows as JSON |
| `POST` | `/match` | `{"ingredient": "1 cup milk"}` | scaled nutrients as JSON |
| `POST` | `/recipe/eval` | `{"lines": [...], "servings": 4}` | aggregate totals as JSON |
| `GET` | `/sources` | — | loaded sources list |

### 7.3 Web UI integration

`GET /` serves the P6 HTML form. `/lookup` and `/recipe/eval` support both
`Accept: text/html` (returns rendered fragment) and `Accept: application/json`
(returns JSON).

### 7.4 Validation

Tests in `tests/test_server.py` using Flask's test client. Cover happy paths
and 400/404 error responses for each endpoint.

---

## P8: LLM ingredient matching

Goal: fall back to an LLM when the regex parser cannot parse an ingredient
string, improving real-world recipe coverage.

### 8.1 Provider abstraction

New `ew/llm.py` with an abstract `LLMProvider` interface:

```python
class LLMProvider(Protocol):
    def extract_ingredient(self, text: str) -> dict | None:
        """Return {"amount": float, "unit": str|None, "food": str} or None."""
```

### 8.2 Built-in providers

- `AnthropicProvider` — uses `claude-haiku-4-5` for low latency and cost
- `OllamaProvider` — calls a local Ollama instance; no API key required
- Provider selected via `--llm-provider anthropic|ollama|none` flag (default: `none`)

### 8.3 Structured output

Prompt instructs the model to return a single JSON object with `amount`,
`unit`, and `food` keys. Response validated before use; falls back to 1 g with
a warning on parse failure.

### 8.4 Response cache

Parsed results cached in `work/llm_cache.sqlite` keyed on the normalised input
string. Cache is hit before any API call. TTL: 7 days.

### 8.5 Integration point

`parse_ingredient()` returns `None` for strings it cannot handle. The CLI
commands (`match`, `recipe eval`) check for `None` and, if a provider is
configured, call `llm.extract_ingredient()` as a fallback.

### 8.6 Validation

Tests in `tests/test_llm.py` using a mock provider. Cover: cache hit/miss,
malformed LLM response handling, fallback behaviour when provider is `none`.

---

## Deferred

These are out of scope for the current roadmap:

- Cross-source food deduplication (e.g., "almonds" in CNF vs. USDA foundation vs. SR legacy)
- User recipe repository (Google Docs integration)
- Fridge/pantry tracking
- Glycemic index data (not in CNF or USDA FDC; requires a separate source)
- iOS/macOS native UI
- CNF update/delta file processing
