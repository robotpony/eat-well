"""Database connection, schema creation, and FTS management."""

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

# Display rank for well-known nutrients (USDA SR numbers).
# Lower rank = shown first on a nutrition label.
NUTRIENT_RANK: dict[int, int] = {
    208: 10,   # Energy (kcal)
    268: 11,   # Energy (kJ)
    203: 100,  # Protein
    204: 200,  # Total fat
    606: 210,  # Saturated fat
    605: 220,  # Trans fat
    601: 230,  # Cholesterol
    205: 300,  # Carbohydrate
    291: 310,  # Fibre
    269: 320,  # Total sugars
    307: 400,  # Sodium
    306: 410,  # Potassium
    301: 420,  # Calcium
    303: 430,  # Iron
    304: 440,  # Magnesium
    305: 450,  # Phosphorus
    309: 460,  # Zinc
    312: 470,  # Copper
    315: 480,  # Manganese
    317: 490,  # Selenium
    401: 500,  # Vitamin C
    320: 600,  # Vitamin A (RAE)
    318: 601,  # Vitamin A (IU)
    328: 610,  # Vitamin D (µg)
    324: 611,  # Vitamin D (IU)
    323: 620,  # Vitamin E
    430: 630,  # Vitamin K
    404: 700,  # Thiamin (B1)
    405: 710,  # Riboflavin (B2)
    406: 720,  # Niacin (B3)
    415: 730,  # Vitamin B6
    417: 740,  # Folate (DFE)
    418: 750,  # Vitamin B12
    421: 760,  # Choline
}

_CREATE_TABLES = """\
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS source (
    id      INTEGER PRIMARY KEY,
    code    TEXT NOT NULL UNIQUE,
    name    TEXT NOT NULL,
    version TEXT
);

CREATE TABLE IF NOT EXISTS nutrient (
    id      INTEGER PRIMARY KEY,
    sr_nbr  INTEGER NOT NULL UNIQUE,
    symbol  TEXT,
    name_en TEXT NOT NULL,
    name_fr TEXT,
    unit    TEXT NOT NULL,
    rank    INTEGER
);

CREATE TABLE IF NOT EXISTS food_category (
    id         INTEGER PRIMARY KEY,
    source_id  INTEGER NOT NULL REFERENCES source(id),
    source_key TEXT NOT NULL,
    name_en    TEXT NOT NULL,
    name_fr    TEXT,
    UNIQUE (source_id, source_key)
);

CREATE TABLE IF NOT EXISTS food (
    id              INTEGER PRIMARY KEY,
    source_id       INTEGER NOT NULL REFERENCES source(id),
    source_food_id  TEXT NOT NULL,
    name_en         TEXT NOT NULL,
    name_fr         TEXT,
    scientific_name TEXT,
    category_id     INTEGER REFERENCES food_category(id),
    UNIQUE (source_id, source_food_id)
);

CREATE TABLE IF NOT EXISTS food_nutrient (
    id          INTEGER PRIMARY KEY,
    food_id     INTEGER NOT NULL REFERENCES food(id),
    nutrient_id INTEGER NOT NULL REFERENCES nutrient(id),
    amount      REAL NOT NULL,
    std_error   REAL,
    n_obs       INTEGER,
    UNIQUE (food_id, nutrient_id)
);

CREATE TABLE IF NOT EXISTS food_portion (
    id          INTEGER PRIMARY KEY,
    food_id     INTEGER NOT NULL REFERENCES food(id),
    measure_en  TEXT NOT NULL,
    measure_fr  TEXT,
    gram_weight REAL NOT NULL,
    seq_num     INTEGER
);

-- User-defined food name aliases (P9a).
-- Merged with bundled aliases from ew/data/aliases.json; user entries win on conflict.
CREATE TABLE IF NOT EXISTS user_food_alias (
    id          INTEGER PRIMARY KEY,
    input_key   TEXT NOT NULL UNIQUE,
    replacement TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

-- User-cached gram resolutions from interactive recipe eval sessions (P9c).
-- Keyed by (food_query, unit); consulted by resolve_grams() before the 1 g fallback.
-- unit is NULL for piece-count items with no unit word.
CREATE TABLE IF NOT EXISTS user_portion_cache (
    id          INTEGER PRIMARY KEY,
    food_query  TEXT NOT NULL,
    unit        TEXT,
    gram_weight REAL NOT NULL,
    created_at  TEXT NOT NULL,
    UNIQUE (food_query, unit)
);
"""

_CREATE_FTS = """\
CREATE VIRTUAL TABLE IF NOT EXISTS food_fts USING fts5(
    name_en,
    name_fr,
    content=food,
    content_rowid=id
);
"""


def connect(path: Path | str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_CREATE_TABLES)
    conn.executescript(_CREATE_FTS)
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    if row is None:
        conn.execute("INSERT INTO schema_version VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()


def rebuild_fts(conn: sqlite3.Connection) -> None:
    """Drop and repopulate the full-text search index from the food table."""
    conn.execute("INSERT INTO food_fts(food_fts) VALUES('delete-all')")
    conn.execute(
        "INSERT INTO food_fts(rowid, name_en, name_fr) "
        "SELECT id, name_en, COALESCE(name_fr, '') FROM food"
    )
