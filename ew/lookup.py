"""FTS search and nutrition label rendering for `ew lookup`."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Optional

from rich.console import Console
from rich.table import Table


# Rank boundaries that define label sections (matches NUTRIENT_RANK in db.py).
SECTIONS = [
    ("Energy",   0,    99),
    ("Macros",  100,   399),
    ("Minerals", 400,  499),
    ("Vitamins", 500, 9999),
]


@dataclass
class FoodMatch:
    id: int
    name: str
    source_name: str
    source_code: str


def search(
    conn: sqlite3.Connection,
    query: str,
    lang: str = "en",
    limit: int = 5,
) -> list[FoodMatch]:
    """FTS5 BM25 search against the food_fts index.

    Searches the name_en column by default; name_fr when lang='fr'.
    Returns up to *limit* matches ordered best-first.

    Fetches a wider candidate set from FTS and applies a lightweight
    re-ranking pass that prefers food names starting with a query term
    (e.g. "Avocado, raw" over "Oil, avocado" for the query "avocado").
    BM25 order is preserved as a stable tiebreaker within each group.
    """
    col = "name_fr" if lang == "fr" else "name_en"
    fts_query = _build_fts_query(query, col)
    # Fetch a wider candidate pool so re-ranking has something to work with.
    fetch_limit = max(limit * 4, 20)
    try:
        rows = conn.execute(
            f"""
            SELECT f.id,
                   COALESCE(f.{col}, f.name_en) AS name,
                   s.name                        AS source_name,
                   s.code                        AS source_code
            FROM food_fts
            JOIN food   f ON food_fts.rowid = f.id
            JOIN source s ON f.source_id    = s.id
            WHERE food_fts MATCH ?
            ORDER BY bm25(food_fts)
            LIMIT ?
            """,
            (fts_query, fetch_limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    matches = [
        FoodMatch(r["id"], r["name"] or "", r["source_name"], r["source_code"])
        for r in rows
    ]
    return _rerank(matches, query)[:limit]


def get_food(conn: sqlite3.Connection, food_id: int) -> Optional[sqlite3.Row]:
    """Return a food row with source name, or None if not found."""
    return conn.execute(
        """
        SELECT f.id, f.name_en, f.name_fr,
               s.name AS source_name,
               s.code AS source_code
        FROM food f
        JOIN source s ON f.source_id = s.id
        WHERE f.id = ?
        """,
        (food_id,),
    ).fetchone()


def get_nutrients(
    conn: sqlite3.Connection,
    food_id: int,
    grams: float = 100.0,
) -> list[sqlite3.Row]:
    """Return nutrient rows scaled to *grams*.

    Values are per 100 g in the database; this scales them linearly.
    Rows where the stored amount is zero are excluded.
    """
    return conn.execute(
        """
        SELECT n.name_en,
               n.name_fr,
               n.unit,
               COALESCE(n.rank, 99999) AS rank,
               fn.amount * ? / 100.0   AS value
        FROM food_nutrient fn
        JOIN nutrient n ON fn.nutrient_id = n.id
        WHERE fn.food_id = ?
          AND fn.amount  > 0
        ORDER BY COALESCE(n.rank, 99999)
        """,
        (grams, food_id),
    ).fetchall()


def get_portions(conn: sqlite3.Connection, food_id: int) -> list[sqlite3.Row]:
    """Return portion measures ordered by seq_num."""
    return conn.execute(
        """
        SELECT measure_en, measure_fr, gram_weight
        FROM food_portion
        WHERE food_id = ?
        ORDER BY seq_num
        """,
        (food_id,),
    ).fetchall()


def render_label(
    console: Console,
    food: sqlite3.Row,
    nutrients: list[sqlite3.Row],
    portions: list[sqlite3.Row],
    per_grams: Optional[float] = None,
    lang: str = "en",
) -> None:
    """Print a two-column nutrition label to *console*.

    *nutrients* must be pre-fetched at 100 g (the default from get_nutrients).
    The second column is *per_grams* when supplied, otherwise the first portion.
    If neither is available, only the per-100-g column is shown.
    """
    # Resolve second column
    if per_grams is not None:
        col2_grams: Optional[float] = per_grams
        col2_label = f"per {per_grams:g} g"
    elif portions:
        first = portions[0]
        col2_grams = first["gram_weight"]
        measure = (
            first["measure_fr"]
            if lang == "fr" and first["measure_fr"]
            else first["measure_en"]
        )
        col2_label = f"{measure}  ({col2_grams:g} g)"
    else:
        col2_grams = None
        col2_label = None

    # Header
    display_name = (
        food["name_fr"] if lang == "fr" and food["name_fr"] else food["name_en"]
    )
    console.print()
    console.print(f"[bold]{display_name}[/bold]  [dim]{food['source_name']}[/dim]")
    console.print()

    # Table
    has_col2 = col2_label is not None
    tbl = Table(box=None, show_header=True, padding=(0, 2), show_edge=False)
    tbl.add_column("", no_wrap=True, min_width=30)
    tbl.add_column("per 100 g", justify="right", style="green")
    if has_col2:
        tbl.add_column(col2_label, justify="right", style="cyan")

    _populate_table(tbl, nutrients, col2_grams, lang, has_col2)
    console.print(tbl)
    console.print()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _populate_table(
    tbl: Table,
    nutrients: list[sqlite3.Row],
    col2_grams: Optional[float],
    lang: str,
    has_col2: bool,
) -> None:
    """Bucket nutrients into sections and add rows with section headers."""
    buckets: dict[str, list] = {name: [] for name, *_ in SECTIONS}
    buckets["Other"] = []

    for row in nutrients:
        rank = row["rank"]
        placed = False
        for section_name, lo, hi in SECTIONS:
            if lo <= rank <= hi:
                buckets[section_name].append(row)
                placed = True
                break
        if not placed:
            buckets["Other"].append(row)

    section_order = [name for name, *_ in SECTIONS] + ["Other"]
    first_section = True
    for section_name in section_order:
        rows = buckets[section_name]
        if not rows:
            continue
        if not first_section:
            _add_row(tbl, "", "", "", has_col2)
        first_section = False
        _add_row(tbl, f"[bold]{section_name}[/bold]", "", "", has_col2)
        for n in rows:
            name = n["name_fr"] if lang == "fr" and n["name_fr"] else n["name_en"]
            val_100 = fmt_value(n["value"], n["unit"])
            val_2 = fmt_value(n["value"] * col2_grams / 100.0, n["unit"]) if col2_grams else ""
            _add_row(tbl, f"  {name}", val_100, val_2, has_col2)


def _add_row(tbl: Table, name: str, val_100: str, val_2: str, has_col2: bool) -> None:
    if has_col2:
        tbl.add_row(name, val_100, val_2)
    else:
        tbl.add_row(name, val_100)


def fmt_value(value: float, unit: str) -> str:
    """Format a nutrient value with its unit."""
    if value >= 1000:
        return f"{value:,.0f} {unit}"
    if value >= 100:
        return f"{value:.0f} {unit}"
    if value >= 10:
        return f"{value:.1f} {unit}"
    if value >= 1:
        return f"{value:.2f} {unit}"
    if value >= 0.01:
        return f"{value:.3f} {unit}"
    return f"{value:.4f} {unit}"


def _rerank(matches: list[FoodMatch], query: str) -> list[FoodMatch]:
    """Stable-sort FTS candidates to prefer names that lead with a query term.

    BM25 sometimes promotes long compound names (e.g. "Oil, avocado") above
    shorter, more direct matches (e.g. "Avocado, raw") because term frequency
    in a longer document inflates the score.  Grouping by whether the food's
    first name component appears in the query (or is a simple plural of a query
    word), then preserving BM25 order within each group, corrects the most
    common cases without introducing new errors for multi-word queries.

    Plural handling: "Onions, raw" has first word "onions"; stripping one
    trailing "s" gives "onion" which matches the query word — so it lands in
    group 0 alongside "Onion dip, regular", and BM25 order decides between them
    (favouring the shorter, more relevant document).
    """
    query_words = set(re.findall(r"\w+", query.lower()))

    def _key(m: FoodMatch) -> int:
        first = (re.findall(r"\w+", m.name.lower()) or [""])[0]
        # Strip one trailing "s" as a minimal plural stem (onions → onion).
        # Guard len > 3 to avoid mangling short words (e.g. "as", "gas").
        first_stem = first[:-1] if first.endswith("s") and len(first) > 3 else first
        return 0 if (first in query_words or first_stem in query_words) else 1

    return sorted(matches, key=_key)  # Python sort is stable


def _build_fts_query(query: str, col: str) -> str:
    """Build a column-filtered FTS5 query from a plain-text search string.

    Each token is emitted as a prefix query (e.g. ``"onion"*``) so that both
    the singular and plural forms of a food name appear in the candidate pool.
    Without prefix matching, the exact-token query ``"onion"`` never matches
    ``"Onions, raw"`` because FTS5 tokenises that document as ``onions``
    (a different token), so the correct result is invisible to the re-ranker.

    Special FTS5 syntax characters are stripped to avoid parse errors.
    Short tokens (≤ 3 characters) use exact matching to avoid noisy prefix
    expansions (e.g. ``"of"*`` would match ``offal``, ``official``, etc.).
    """
    clean = re.sub(r'["\(\)\*\^\+\:\,\.\/]', " ", query)
    words = clean.split()
    if not words:
        return query
    quoted = " ".join(f'"{w}"*' if len(w) > 3 else f'"{w}"' for w in words)
    return f"{col} : {quoted}"
