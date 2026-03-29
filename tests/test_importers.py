"""Tests for CNF and USDA importers."""

import pytest

from ew.importers.cnf import CnfImporter
from ew.importers.usda import UsaImporter


# ---------------------------------------------------------------------------
# CNF importer
# ---------------------------------------------------------------------------


def test_cnf_imports_food_groups(db, cnf_dir):
    CnfImporter(db).run(cnf_dir)
    rows = db.execute("SELECT * FROM food_category ORDER BY source_key").fetchall()
    assert len(rows) == 2
    dairy = next(r for r in rows if r["source_key"] == "1")
    assert dairy["name_en"] == "Dairy and Egg Products"
    assert dairy["name_fr"] == "Produits laitiers"


def test_cnf_imports_nutrients(db, cnf_dir):
    CnfImporter(db).run(cnf_dir)
    rows = db.execute("SELECT sr_nbr, name_en, name_fr, unit FROM nutrient ORDER BY sr_nbr").fetchall()
    assert len(rows) == 2
    protein = rows[0]
    assert protein["sr_nbr"] == 203
    assert protein["name_en"] == "PROTEIN"
    assert protein["name_fr"] == "PROTEINES"
    assert protein["unit"] == "g"


def test_cnf_imports_foods(db, cnf_dir):
    CnfImporter(db).run(cnf_dir)
    rows = db.execute("SELECT * FROM food ORDER BY source_food_id").fetchall()
    assert len(rows) == 2
    milk = rows[0]
    assert milk["name_en"] == "Whole milk"
    assert milk["name_fr"] == "Lait entier"
    assert milk["scientific_name"] == "Bos taurus"


def test_cnf_food_linked_to_category(db, cnf_dir):
    CnfImporter(db).run(cnf_dir)
    row = db.execute(
        "SELECT fc.name_en FROM food f JOIN food_category fc ON fc.id = f.category_id "
        "WHERE f.name_en = 'Whole milk'"
    ).fetchone()
    assert row is not None
    assert row["name_en"] == "Dairy and Egg Products"


def test_cnf_imports_nutrient_amounts(db, cnf_dir):
    CnfImporter(db).run(cnf_dir)
    rows = db.execute("SELECT COUNT(*) AS n FROM food_nutrient").fetchone()
    assert rows["n"] == 3  # 2 for milk, 1 for apple


def test_cnf_nutrient_amount_values(db, cnf_dir):
    CnfImporter(db).run(cnf_dir)
    row = db.execute(
        "SELECT fn.amount FROM food_nutrient fn "
        "JOIN food f ON f.id = fn.food_id "
        "JOIN nutrient n ON n.id = fn.nutrient_id "
        "WHERE f.name_en = 'Whole milk' AND n.sr_nbr = 203"
    ).fetchone()
    assert row is not None
    assert abs(row["amount"] - 3.2) < 0.001


def test_cnf_gram_weight_calculation(db, cnf_dir):
    """CNF ConversionFactorValue * 100 = gram_weight."""
    CnfImporter(db).run(cnf_dir)
    row = db.execute(
        "SELECT fp.gram_weight FROM food_portion fp "
        "JOIN food f ON f.id = fp.food_id "
        "WHERE f.name_en = 'Whole milk' AND fp.measure_en = '1 cup'"
    ).fetchone()
    assert row is not None
    assert abs(row["gram_weight"] - 244.0) < 0.01  # factor 2.44 * 100


def test_cnf_portions_have_french_labels(db, cnf_dir):
    CnfImporter(db).run(cnf_dir)
    row = db.execute(
        "SELECT fp.measure_fr FROM food_portion fp "
        "JOIN food f ON f.id = fp.food_id "
        "WHERE f.name_en = 'Whole milk' AND fp.measure_en = '1 cup'"
    ).fetchone()
    assert row is not None
    assert row["measure_fr"] == "1 tasse"


def test_cnf_source_registered(db, cnf_dir):
    CnfImporter(db).run(cnf_dir)
    row = db.execute("SELECT * FROM source WHERE code = 'cnf'").fetchone()
    assert row is not None
    assert row["version"] == "2015"


# ---------------------------------------------------------------------------
# USDA importer
# ---------------------------------------------------------------------------


def test_usda_imports_categories(db, usda_dir):
    UsaImporter(db).run(usda_dir, "usda_test", "USDA Test", "2023")
    rows = db.execute("SELECT * FROM food_category ORDER BY source_key").fetchall()
    assert len(rows) == 2
    dairy = next(r for r in rows if r["source_key"] == "1")
    assert dairy["name_en"] == "Dairy and Egg Products"


def test_usda_imports_nutrients(db, usda_dir):
    UsaImporter(db).run(usda_dir, "usda_test", "USDA Test", "2023")
    rows = db.execute("SELECT sr_nbr, name_en, unit FROM nutrient ORDER BY sr_nbr").fetchall()
    assert len(rows) == 3
    protein = next(r for r in rows if r["sr_nbr"] == 203)
    assert protein["name_en"] == "Protein"
    assert protein["unit"] == "g"


def test_usda_imports_foods(db, usda_dir):
    UsaImporter(db).run(usda_dir, "usda_test", "USDA Test", "2023")
    rows = db.execute("SELECT name_en FROM food ORDER BY name_en").fetchall()
    names = [r["name_en"] for r in rows]
    assert "Milk, whole" in names
    assert "Apples, raw" in names


def test_usda_food_linked_to_category(db, usda_dir):
    UsaImporter(db).run(usda_dir, "usda_test", "USDA Test", "2023")
    row = db.execute(
        "SELECT fc.name_en FROM food f JOIN food_category fc ON fc.id = f.category_id "
        "WHERE f.name_en = 'Milk, whole'"
    ).fetchone()
    assert row is not None
    assert row["name_en"] == "Dairy and Egg Products"


def test_usda_imports_food_nutrients(db, usda_dir):
    UsaImporter(db).run(usda_dir, "usda_test", "USDA Test", "2023")
    row = db.execute(
        "SELECT fn.amount FROM food_nutrient fn "
        "JOIN food f ON f.id = fn.food_id "
        "JOIN nutrient n ON n.id = fn.nutrient_id "
        "WHERE f.name_en = 'Milk, whole' AND n.sr_nbr = 203"
    ).fetchone()
    assert row is not None
    assert abs(row["amount"] - 3.2) < 0.001


def test_usda_imports_portions(db, usda_dir):
    UsaImporter(db).run(usda_dir, "usda_test", "USDA Test", "2023")
    rows = db.execute(
        "SELECT fp.measure_en, fp.gram_weight FROM food_portion fp "
        "JOIN food f ON f.id = fp.food_id "
        "WHERE f.name_en = 'Milk, whole' "
        "ORDER BY fp.seq_num"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["measure_en"] == "1 cup"
    assert abs(rows[0]["gram_weight"] - 244.0) < 0.01


# ---------------------------------------------------------------------------
# Nutrient deduplication across sources
# ---------------------------------------------------------------------------


def test_nutrient_deduplication(db, cnf_dir, usda_dir):
    """Same sr_nbr from CNF then USDA → one nutrient row, USDA name_en wins."""
    CnfImporter(db).run(cnf_dir)
    UsaImporter(db).run(usda_dir, "usda_test", "USDA Test", "2023")

    rows = db.execute("SELECT * FROM nutrient WHERE sr_nbr = 203").fetchall()
    assert len(rows) == 1
    # USDA name overwrites CNF's uppercase name
    assert rows[0]["name_en"] == "Protein"
    # French name from CNF is preserved
    assert rows[0]["name_fr"] == "PROTEINES"


def test_nutrient_rank_set_for_known_nutrients(db, cnf_dir):
    CnfImporter(db).run(cnf_dir)
    row = db.execute("SELECT rank FROM nutrient WHERE sr_nbr = 208").fetchone()
    assert row is not None
    assert row["rank"] == 10  # Energy is rank 10


def test_nutrient_rank_null_for_unknown(db, usda_dir):
    # Add a nutrient not in NUTRIENT_RANK (sr_nbr 999 doesn't exist in rank table)
    import sqlite3
    (usda_dir / "nutrient.csv").write_text(
        "id,name,unit_name,nutrient_nbr,rank\n"
        "9999,Some Obscure Nutrient,MG,999,99999.0\n"
    )
    UsaImporter(db).run(usda_dir, "usda_test", "USDA Test", "2023")
    row = db.execute("SELECT rank FROM nutrient WHERE sr_nbr = 999").fetchone()
    assert row is not None
    assert row["rank"] is None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_cnf_skips_missing_food_in_nutrient_amounts(db, cnf_dir, tmp_path):
    """Nutrient amount rows referencing non-existent foods are skipped silently."""
    d = tmp_path / "cnf_bad"
    import shutil
    shutil.copytree(cnf_dir, d)
    # Append a row referencing food_id 999 which doesn't exist
    with open(d / "NUTRIENT AMOUNT.csv", "a", encoding="latin-1") as f:
        f.write("999,203,5.0,0,0,102,2010-01-01\n")

    CnfImporter(db).run(d)
    # Should still import the valid rows
    count = db.execute("SELECT COUNT(*) FROM food_nutrient").fetchone()[0]
    assert count == 3  # only the 3 valid rows


def test_usda_missing_files_returns_zero_counts(db, tmp_path):
    """Importing from an empty directory returns zero counts without error."""
    empty = tmp_path / "empty"
    empty.mkdir()
    counts = UsaImporter(db).run(empty, "empty", "Empty", "0")
    assert counts["food"] == 0
    assert counts["food_nutrient"] == 0
