"""User-configurable resolution data: aliases, food weights, taste defaults, and portion cache.

Provides a ResolutionContext that bundles all four tables.  CLI commands load
the context once at startup and thread it through parse_ingredient() and
resolve_grams() so the parser never touches the DB or the filesystem directly.

Bundled defaults live in ew/data/*.json.  User overrides live in work/ (same
directory as ew.db).  User data always wins on conflict.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# Bundled reference data shipped inside the package.
_DATA_DIR = Path(__file__).parent / "data"


@dataclass
class ResolutionContext:
    """All user-resolution tables needed by parse_ingredient() and resolve_grams()."""

    aliases: dict[str, str] = field(default_factory=dict)
    food_weights: list[dict] = field(default_factory=list)
    taste_defaults: list[dict] = field(default_factory=list)
    user_cache: dict[tuple[str, Optional[str]], float] = field(default_factory=dict)


def load_context(
    conn: Optional[sqlite3.Connection] = None,
    work_dir: Optional[Path] = None,
) -> ResolutionContext:
    """Load all resolution data, merging bundled defaults with user overrides.

    *conn* is an open connection to work/ew.db (for alias and cache tables).
    *work_dir* is the directory containing work/food_weights.json and other
    user JSON overrides (typically the same parent as ew.db).
    Both parameters are optional; omitting them gives bundled-only data.
    """
    return ResolutionContext(
        aliases=_load_aliases(conn),
        food_weights=_load_food_weights(work_dir),
        taste_defaults=_load_taste_defaults(work_dir),
        user_cache=_load_user_cache(conn) if conn is not None else {},
    )


# ---------------------------------------------------------------------------
# Aliases  (P9a)
# ---------------------------------------------------------------------------

def _load_aliases(conn: Optional[sqlite3.Connection]) -> dict[str, str]:
    """Bundled aliases merged with user DB entries; user entries win on conflict."""
    raw = _load_json_safe(_DATA_DIR / "aliases.json", {})
    merged: dict[str, str] = {k.lower().strip(): v for k, v in raw.items()} if isinstance(raw, dict) else {}
    if conn is not None:
        try:
            for row in conn.execute("SELECT input_key, replacement FROM user_food_alias").fetchall():
                merged[row["input_key"].lower().strip()] = row["replacement"]
        except sqlite3.OperationalError:
            pass  # table not yet created in an older DB
    return merged


def save_alias(conn: sqlite3.Connection, input_key: str, replacement: str) -> None:
    """Upsert an alias into user_food_alias."""
    now = _now()
    conn.execute(
        "INSERT INTO user_food_alias (input_key, replacement, created_at) VALUES (?, ?, ?)"
        " ON CONFLICT(input_key) DO UPDATE SET"
        "   replacement = excluded.replacement,"
        "   created_at  = excluded.created_at",
        (input_key.lower().strip(), replacement.strip(), now),
    )
    conn.commit()


def list_aliases(conn: Optional[sqlite3.Connection]) -> tuple[dict[str, str], list[dict]]:
    """Return (bundled_aliases, user_aliases_list) for display."""
    raw = _load_json_safe(_DATA_DIR / "aliases.json", {})
    bundled: dict[str, str] = raw if isinstance(raw, dict) else {}
    user: list[dict] = []
    if conn is not None:
        try:
            rows = conn.execute(
                "SELECT input_key, replacement, created_at"
                " FROM user_food_alias ORDER BY input_key"
            ).fetchall()
            user = [dict(r) for r in rows]
        except sqlite3.OperationalError:
            pass
    return bundled, user


# ---------------------------------------------------------------------------
# Food weight reference  (P9b)
# ---------------------------------------------------------------------------

def _load_food_weights(work_dir: Optional[Path]) -> list[dict]:
    """Bundled food weights merged with user JSON; user entries prepended (checked first)."""
    bundled: list[dict] = _load_json_safe(_DATA_DIR / "food_weights.json", [])
    user: list[dict] = []
    if work_dir is not None:
        user = _load_json_safe(work_dir / "food_weights.json", [])
    return list(user) + list(bundled)


def save_food_weight(work_dir: Path, food_key: str, unit: str, grams: float) -> None:
    """Upsert one entry into work/food_weights.json."""
    path = work_dir / "food_weights.json"
    existing: list[dict] = _load_json_safe(path, [])
    updated = [
        e for e in existing
        if not (e["key"].lower() == food_key.lower() and e["unit"].lower() == unit.lower())
    ]
    updated.append({"key": food_key.lower(), "unit": unit.lower(), "grams": float(grams)})
    path.write_text(json.dumps(updated, indent=2), encoding="utf-8")


def list_food_weights(work_dir: Optional[Path] = None) -> tuple[list[dict], list[dict]]:
    """Return (bundled_weights, user_weights) for display."""
    bundled: list[dict] = _load_json_safe(_DATA_DIR / "food_weights.json", [])
    user: list[dict] = []
    if work_dir is not None:
        user = _load_json_safe(work_dir / "food_weights.json", [])
    return bundled, user


# ---------------------------------------------------------------------------
# Taste defaults  (P9d)
# ---------------------------------------------------------------------------

def _load_taste_defaults(work_dir: Optional[Path]) -> list[dict]:
    """Bundled taste defaults merged with user JSON; user entries take priority."""
    bundled: list[dict] = _load_json_safe(_DATA_DIR / "taste_defaults.json", [])
    user: list[dict] = []
    if work_dir is not None:
        user = _load_json_safe(work_dir / "taste_defaults.json", [])
    return list(user) + list(bundled)


# ---------------------------------------------------------------------------
# User portion cache  (P9c)
# ---------------------------------------------------------------------------

_UNIT_NULL_SENTINEL = ""  # stored in DB when unit is None (NULL != NULL in SQLite UNIQUE)


def _load_user_cache(conn: sqlite3.Connection) -> dict[tuple[str, Optional[str]], float]:
    """Load the user portion cache from DB into a dict keyed by (food_query, unit).

    Empty-string unit is converted back to None (the Python sentinel for unitless).
    """
    cache: dict[tuple[str, Optional[str]], float] = {}
    try:
        for row in conn.execute(
            "SELECT food_query, unit, gram_weight FROM user_portion_cache"
        ).fetchall():
            unit = row["unit"] or None  # "" → None
            cache[(row["food_query"], unit)] = row["gram_weight"]
    except sqlite3.OperationalError:
        pass
    return cache


def save_portion_cache(
    conn: sqlite3.Connection,
    food_query: str,
    unit: Optional[str],
    gram_weight: float,
) -> None:
    """Upsert one entry into user_portion_cache.

    None unit is stored as "" so the UNIQUE(food_query, unit) constraint works
    correctly (SQLite treats NULL != NULL in unique indexes).
    """
    now = _now()
    unit_stored = unit if unit is not None else _UNIT_NULL_SENTINEL
    conn.execute(
        "INSERT INTO user_portion_cache (food_query, unit, gram_weight, created_at)"
        " VALUES (?, ?, ?, ?)"
        " ON CONFLICT(food_query, unit) DO UPDATE SET"
        "   gram_weight = excluded.gram_weight,"
        "   created_at  = excluded.created_at",
        (food_query, unit_stored, float(gram_weight), now),
    )
    conn.commit()


def list_portion_cache(conn: sqlite3.Connection) -> list[dict]:
    """Return all cached portion entries for display.

    Empty-string unit is converted back to None.
    """
    try:
        rows = conn.execute(
            "SELECT food_query, unit, gram_weight, created_at"
            " FROM user_portion_cache ORDER BY food_query"
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["unit"] = d["unit"] or None
            result.append(d)
        return result
    except sqlite3.OperationalError:
        return []


def clear_portion_cache(conn: sqlite3.Connection) -> None:
    """Delete all entries from user_portion_cache."""
    conn.execute("DELETE FROM user_portion_cache")
    conn.commit()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _load_json_safe(path: Path, default):
    """Read and parse a JSON file, returning *default* on any error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
