"""Canadian Food Nutrient Database (CNF) importer.

Source files expected in a directory:
  FOOD GROUP.csv
  NUTRIENT NAME.csv
  FOOD NAME.csv
  NUTRIENT AMOUNT.csv
  MEASURE NAME.csv
  CONVERSION FACTOR.csv
"""

import sqlite3
from pathlib import Path

from ..db import NUTRIENT_RANK
from .base import normalize_unit, read_csv, batch_insert

SOURCE_CODE = "cnf"
SOURCE_NAME = "Canadian Food Nutrient Database"
SOURCE_VERSION = "2015"

# CNF CSVs are Latin-1 encoded (older Government of Canada export).
_ENCODING = "latin-1"


class CnfImporter:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def run(self, data_dir: Path) -> dict[str, int]:
        """Import all CNF tables. Returns counts per table."""
        counts: dict[str, int] = {}

        source_id = self._ensure_source()
        counts["food_category"] = self._import_food_groups(source_id, data_dir)
        counts["nutrient"] = self._import_nutrients(data_dir)
        counts["food"] = self._import_foods(source_id, data_dir)
        counts["food_nutrient"] = self._import_nutrient_amounts(data_dir)
        counts["food_portion"] = self._import_portions(data_dir)
        self.conn.commit()

        return counts

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_source(self) -> int:
        self.conn.execute(
            "INSERT OR IGNORE INTO source (code, name, version) VALUES (?, ?, ?)",
            (SOURCE_CODE, SOURCE_NAME, SOURCE_VERSION),
        )
        row = self.conn.execute(
            "SELECT id FROM source WHERE code = ?", (SOURCE_CODE,)
        ).fetchone()
        return row["id"]

    def _import_food_groups(self, source_id: int, data_dir: Path) -> int:
        rows = read_csv(data_dir, "FOOD GROUP.csv", _ENCODING)
        data = [
            (
                source_id,
                row["FoodGroupID"].strip(),
                row["FoodGroupName"].strip(),
                row.get("FoodGroupNameF", "").strip() or None,
            )
            for row in rows
        ]
        batch_insert(
            self.conn,
            "INSERT OR IGNORE INTO food_category (source_id, source_key, name_en, name_fr) "
            "VALUES (?, ?, ?, ?)",
            iter(data),
        )
        # Build category map for use by _import_foods
        self._category_map: dict[str, int] = {
            row["source_key"]: row["id"]
            for row in self.conn.execute(
                "SELECT id, source_key FROM food_category WHERE source_id = ?",
                (source_id,),
            ).fetchall()
        }
        return len(data)

    def _import_nutrients(self, data_dir: Path) -> int:
        rows = read_csv(data_dir, "NUTRIENT NAME.csv", _ENCODING)
        data = []
        for row in rows:
            sr_nbr_str = row.get("NutrientCode", "").strip()
            if not sr_nbr_str:
                continue
            try:
                sr_nbr = int(sr_nbr_str)
            except ValueError:
                continue
            data.append((
                sr_nbr,
                row.get("NutrientSymbol", "").strip() or None,
                row["NutrientName"].strip(),
                row.get("NutrientNameF", "").strip() or None,
                normalize_unit(row.get("NutrientUnit", "").strip()),
                NUTRIENT_RANK.get(sr_nbr),
            ))
        batch_insert(
            self.conn,
            "INSERT OR IGNORE INTO nutrient (sr_nbr, symbol, name_en, name_fr, unit, rank) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            iter(data),
        )
        # Update French names on any existing rows (CNF is the only French source)
        for sr_nbr, _sym, _en, name_fr, _unit, _rank in data:
            if name_fr:
                self.conn.execute(
                    "UPDATE nutrient SET name_fr = ? WHERE sr_nbr = ? AND name_fr IS NULL",
                    (name_fr, sr_nbr),
                )
        # Build nutrient map: cnf NutrientID → our nutrient.id
        # CNF NutrientID == NutrientCode == sr_nbr
        self._nutrient_map: dict[str, int] = {
            str(row["sr_nbr"]): row["id"]
            for row in self.conn.execute("SELECT id, sr_nbr FROM nutrient").fetchall()
        }
        return len(data)

    def _import_foods(self, source_id: int, data_dir: Path) -> int:
        rows = read_csv(data_dir, "FOOD NAME.csv", _ENCODING)
        data = []
        for row in rows:
            group_id = self._category_map.get(row.get("FoodGroupID", "").strip())
            data.append((
                source_id,
                row["FoodID"].strip(),
                row["FoodDescription"].strip(),
                row.get("FoodDescriptionF", "").strip() or None,
                row.get("ScientificName", "").strip() or None,
                group_id,
            ))
        batch_insert(
            self.conn,
            "INSERT OR IGNORE INTO food "
            "(source_id, source_food_id, name_en, name_fr, scientific_name, category_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            iter(data),
        )
        # Build food map: cnf FoodID → our food.id
        self._food_map: dict[str, int] = {
            row["source_food_id"]: row["id"]
            for row in self.conn.execute(
                "SELECT id, source_food_id FROM food WHERE source_id = ?",
                (source_id,),
            ).fetchall()
        }
        return len(data)

    def _import_nutrient_amounts(self, data_dir: Path) -> int:
        rows = read_csv(data_dir, "NUTRIENT AMOUNT.csv", _ENCODING)

        def generate():
            for row in rows:
                food_id = self._food_map.get(row["FoodID"].strip())
                nutrient_id = self._nutrient_map.get(row["NutrientID"].strip())
                if food_id is None or nutrient_id is None:
                    continue
                try:
                    amount = float(row["NutrientValue"])
                except (ValueError, KeyError):
                    continue
                std_error = _float_or_none(row.get("StandardError"))
                n_obs = _int_or_none(row.get("NumberofObservations"))
                yield (food_id, nutrient_id, amount, std_error, n_obs)

        return batch_insert(
            self.conn,
            "INSERT OR IGNORE INTO food_nutrient "
            "(food_id, nutrient_id, amount, std_error, n_obs) VALUES (?, ?, ?, ?, ?)",
            generate(),
        )

    def _import_portions(self, data_dir: Path) -> int:
        measure_rows = read_csv(data_dir, "MEASURE NAME.csv", _ENCODING)
        # measure_map: MeasureID → (desc_en, desc_fr)
        measure_map: dict[str, tuple[str, str | None]] = {}
        for row in measure_rows:
            mid = row.get("MeasureID", "").strip()
            if not mid:
                continue
            en = row.get("MeasureDescription", "").strip()
            fr = row.get("MeasureDescriptionF", "").strip() or None
            measure_map[mid] = (en, fr)

        cf_rows = read_csv(data_dir, "CONVERSION FACTOR.csv", _ENCODING)

        def generate():
            for i, row in enumerate(cf_rows):
                food_id = self._food_map.get(row["FoodID"].strip())
                if food_id is None:
                    continue
                mid = row.get("MeasureID", "").strip()
                measure = measure_map.get(mid)
                if measure is None:
                    continue
                try:
                    factor = float(row["ConversionFactorValue"])
                except (ValueError, KeyError):
                    continue
                gram_weight = factor * 100.0
                yield (food_id, measure[0], measure[1], gram_weight, i)

        return batch_insert(
            self.conn,
            "INSERT INTO food_portion (food_id, measure_en, measure_fr, gram_weight, seq_num) "
            "VALUES (?, ?, ?, ?, ?)",
            generate(),
        )


def _float_or_none(val: str | None) -> float | None:
    if val is None:
        return None
    s = val.strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _int_or_none(val: str | None) -> int | None:
    if val is None:
        return None
    s = val.strip()
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None
