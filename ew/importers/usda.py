"""USDA FoodData Central importer.

Handles three dataset types from a directory or zip archive:
  - Foundation foods  (directory: FoodData_Central_foundation_food_csv_*)
  - SR Legacy         (zip: FoodData_Central_sr_legacy_food_csv_*.zip)
  - Survey / FNDDS    (zip: FoodData_Central_survey_food_csv_*.zip)

All three share the same core CSV structure:
  food.csv, nutrient.csv, food_nutrient.csv, food_portion.csv

Category file varies:
  - Foundation: no food_category.csv in the export → foods get NULL category_id
  - SR Legacy:  food_category.csv
  - Survey:     wweia_food_category.csv
"""

import sqlite3
from pathlib import Path

from ..db import NUTRIENT_RANK
from .base import normalize_unit, read_csv, batch_insert


class UsaImporter:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def run(
        self,
        data_path: Path,
        source_code: str,
        source_name: str,
        source_version: str,
    ) -> dict[str, int]:
        """Import one USDA dataset. Returns counts per table."""
        counts: dict[str, int] = {}

        source_id = self._ensure_source(source_code, source_name, source_version)
        counts["food_category"] = self._import_categories(source_id, data_path)
        counts["nutrient"] = self._import_nutrients(data_path)
        counts["food"] = self._import_foods(source_id, data_path)
        counts["food_nutrient"] = self._import_food_nutrients(data_path)
        counts["food_portion"] = self._import_portions(data_path)
        self.conn.commit()

        return counts

    # ------------------------------------------------------------------

    def _ensure_source(self, code: str, name: str, version: str) -> int:
        self.conn.execute(
            "INSERT OR IGNORE INTO source (code, name, version) VALUES (?, ?, ?)",
            (code, name, version),
        )
        return self.conn.execute(
            "SELECT id FROM source WHERE code = ?", (code,)
        ).fetchone()["id"]

    def _import_categories(self, source_id: int, data_path: Path) -> int:
        # Try standard food_category.csv first, then WWEIA variant.
        rows = read_csv(data_path, "food_category.csv")
        if rows:
            key_col, name_col = "id", "description"
        else:
            rows = read_csv(data_path, "wweia_food_category.csv")
            key_col, name_col = "wweia_food_category_code", "wweia_food_category_description"

        if not rows:
            self._category_map: dict[str, int] = {}
            return 0

        data = [
            (source_id, str(r[key_col]).strip(), r[name_col].strip())
            for r in rows
            if r.get(key_col) and r.get(name_col)
        ]
        batch_insert(
            self.conn,
            "INSERT OR IGNORE INTO food_category (source_id, source_key, name_en) VALUES (?, ?, ?)",
            iter(data),
        )
        self._category_map = {
            row["source_key"]: row["id"]
            for row in self.conn.execute(
                "SELECT id, source_key FROM food_category WHERE source_id = ?", (source_id,)
            ).fetchall()
        }
        return len(data)

    def _import_nutrients(self, data_path: Path) -> int:
        rows = read_csv(data_path, "nutrient.csv")
        if not rows:
            self._nutrient_map: dict[str, int] = {}
            return 0

        data = []
        for row in rows:
            nbr_str = row.get("nutrient_nbr", "").strip()
            if not nbr_str:
                continue
            try:
                sr_nbr = int(float(nbr_str))
            except ValueError:
                continue
            usda_id = row.get("id", "").strip()
            name_en = row.get("name", "").strip()
            unit = normalize_unit(row.get("unit_name", "").strip())
            data.append((sr_nbr, name_en, unit, NUTRIENT_RANK.get(sr_nbr), usda_id))

        for sr_nbr, name_en, unit, rank, _usda_id in data:
            # Upsert: insert new rows; for existing rows, update name_en (USDA is more precise)
            # and fill in rank / unit if not yet set.
            self.conn.execute(
                """
                INSERT INTO nutrient (sr_nbr, name_en, unit, rank)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(sr_nbr) DO UPDATE SET
                    name_en = excluded.name_en,
                    unit    = excluded.unit,
                    rank    = COALESCE(nutrient.rank, excluded.rank)
                """,
                (sr_nbr, name_en, unit, rank),
            )

        # Build map: usda nutrient.id (string) → our nutrient.id
        # We stored usda_id alongside sr_nbr; join via sr_nbr.
        sr_to_ours = {
            str(row["sr_nbr"]): row["id"]
            for row in self.conn.execute("SELECT id, sr_nbr FROM nutrient").fetchall()
        }
        self._nutrient_map = {}
        for sr_nbr, _name, _unit, _rank, usda_id in data:
            ours = sr_to_ours.get(str(sr_nbr))
            if ours and usda_id:
                self._nutrient_map[usda_id] = ours

        return len(data)

    def _import_foods(self, source_id: int, data_path: Path) -> int:
        rows = read_csv(data_path, "food.csv")
        data = []
        for row in rows:
            fdc_id = row.get("fdc_id", "").strip()
            name_en = row.get("description", "").strip()
            if not fdc_id or not name_en:
                continue
            cat_key = row.get("food_category_id", "").strip()
            category_id = self._category_map.get(cat_key)
            data.append((source_id, fdc_id, name_en, category_id))

        batch_insert(
            self.conn,
            "INSERT OR IGNORE INTO food (source_id, source_food_id, name_en, category_id) "
            "VALUES (?, ?, ?, ?)",
            iter(data),
        )
        self._food_map: dict[str, int] = {
            row["source_food_id"]: row["id"]
            for row in self.conn.execute(
                "SELECT id, source_food_id FROM food WHERE source_id = ?", (source_id,)
            ).fetchall()
        }
        return len(data)

    def _import_food_nutrients(self, data_path: Path) -> int:
        rows = read_csv(data_path, "food_nutrient.csv")

        def generate():
            for row in rows:
                food_id = self._food_map.get(row.get("fdc_id", "").strip())
                nutrient_id = self._nutrient_map.get(row.get("nutrient_id", "").strip())
                if food_id is None or nutrient_id is None:
                    continue
                try:
                    amount = float(row["amount"])
                except (ValueError, KeyError, TypeError):
                    continue
                std_err = _float_or_none(row.get("std_error") or row.get("std_dev"))
                n_obs = _int_or_none(row.get("data_points"))
                yield (food_id, nutrient_id, amount, std_err, n_obs)

        return batch_insert(
            self.conn,
            "INSERT OR IGNORE INTO food_nutrient "
            "(food_id, nutrient_id, amount, std_error, n_obs) VALUES (?, ?, ?, ?, ?)",
            generate(),
        )

    def _import_portions(self, data_path: Path) -> int:
        # Load unit names: measure_unit_id → abbreviation or name
        unit_rows = read_csv(data_path, "measure_unit.csv")
        unit_map: dict[str, str] = {}
        for row in unit_rows:
            uid = row.get("id", "").strip()
            label = (row.get("abbreviation") or row.get("name") or "").strip()
            if uid and label:
                unit_map[uid] = label

        rows = read_csv(data_path, "food_portion.csv")

        def generate():
            for row in rows:
                food_id = self._food_map.get(row.get("fdc_id", "").strip())
                if food_id is None:
                    continue
                try:
                    gram_weight = float(row["gram_weight"])
                except (ValueError, KeyError, TypeError):
                    continue
                amount_str = row.get("amount", "").strip()
                unit_id = row.get("measure_unit_id", "").strip()
                portion_desc = row.get("portion_description", "").strip()
                modifier = row.get("modifier", "").strip()
                seq_str = row.get("seq_num", "").strip()
                seq_num = _int_or_none(seq_str)

                label = _build_measure_label(amount_str, unit_id, unit_map, portion_desc, modifier)
                yield (food_id, label, gram_weight, seq_num)

        return batch_insert(
            self.conn,
            "INSERT INTO food_portion (food_id, measure_en, gram_weight, seq_num) "
            "VALUES (?, ?, ?, ?)",
            generate(),
        )


def _build_measure_label(
    amount_str: str,
    unit_id: str,
    unit_map: dict[str, str],
    portion_desc: str,
    modifier: str,
) -> str:
    """Construct a human-readable portion label."""
    # Format amount: drop unnecessary decimal (2.0 → "2", 0.25 → "0.25")
    try:
        amount_f = float(amount_str)
        amount_label = f"{amount_f:g}"
    except (ValueError, TypeError):
        amount_label = amount_str

    unit_label = unit_map.get(unit_id, "")

    if portion_desc:
        parts = [p for p in [amount_label, portion_desc, modifier] if p]
        return " ".join(parts)
    elif unit_label:
        return f"{amount_label} {unit_label}".strip()
    else:
        return f"{amount_label}g"


def _float_or_none(val) -> float | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _int_or_none(val) -> int | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None
