"""Tests for schema creation and FTS."""

from ew.db import connect, create_schema, rebuild_fts, SCHEMA_VERSION


def test_schema_creates_all_tables(db):
    tables = {
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    expected = {
        "schema_version",
        "source",
        "nutrient",
        "food_category",
        "food",
        "food_nutrient",
        "food_portion",
    }
    assert expected.issubset(tables)


def test_schema_creates_fts_table(db):
    row = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='food_fts'"
    ).fetchone()
    assert row is not None


def test_schema_version_recorded(db):
    row = db.execute("SELECT version FROM schema_version").fetchone()
    assert row is not None
    assert row["version"] == SCHEMA_VERSION


def test_create_schema_is_idempotent(db):
    # Calling create_schema twice should not raise.
    create_schema(db)
    create_schema(db)
    rows = db.execute("SELECT version FROM schema_version").fetchall()
    assert len(rows) == 1


def test_rebuild_fts_indexes_foods(db):
    db.execute("INSERT INTO source (code, name) VALUES ('test', 'Test')")
    source_id = db.execute("SELECT id FROM source WHERE code='test'").fetchone()["id"]
    db.execute(
        "INSERT INTO food (source_id, source_food_id, name_en, name_fr) VALUES (?, ?, ?, ?)",
        (source_id, "1", "raw almonds", "amandes crues"),
    )
    db.commit()

    rebuild_fts(db)
    db.commit()

    row = db.execute(
        "SELECT rowid FROM food_fts WHERE food_fts MATCH 'almonds'"
    ).fetchone()
    assert row is not None

    row = db.execute(
        "SELECT rowid FROM food_fts WHERE food_fts MATCH 'amandes'"
    ).fetchone()
    assert row is not None


def test_fts_returns_no_results_before_rebuild(db):
    db.execute("INSERT INTO source (code, name) VALUES ('test', 'Test')")
    source_id = db.execute("SELECT id FROM source WHERE code='test'").fetchone()["id"]
    db.execute(
        "INSERT INTO food (source_id, source_food_id, name_en) VALUES (?, ?, ?)",
        (source_id, "1", "broccoli"),
    )
    db.commit()
    # FTS not yet rebuilt — no results
    row = db.execute(
        "SELECT rowid FROM food_fts WHERE food_fts MATCH 'broccoli'"
    ).fetchone()
    assert row is None
