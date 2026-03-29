"""Shared utilities for all importers."""

import csv
import io
import zipfile
from pathlib import Path
from typing import Iterator

BATCH_SIZE = 5_000

# Normalize unit strings to a consistent form.
_UNIT_MAP = {
    "g": "g",
    "mg": "mg",
    "ug": "µg",
    "µg": "µg",
    "mcg": "µg",
    "kcal": "kcal",
    "kj": "kJ",
    "iu": "IU",
    "sp_gr": "sp_gr",
}


def normalize_unit(unit: str) -> str:
    return _UNIT_MAP.get(unit.strip().lower(), unit.strip().lower())


def read_csv(
    source: Path,
    filename: str,
    encoding: str = "utf-8",
) -> list[dict]:
    """Read a CSV file from a directory or zip archive.

    Returns a list of row dicts. Returns an empty list if the file is not found.
    """
    if source.suffix == ".zip":
        try:
            zf = zipfile.ZipFile(source)
        except (zipfile.BadZipFile, FileNotFoundError):
            return []
        matches = [n for n in zf.namelist() if n.endswith(f"/{filename}") or n == filename]
        if not matches:
            return []
        with zf.open(matches[0]) as raw:
            text = raw.read().decode(encoding, errors="replace")
        return list(csv.DictReader(io.StringIO(text)))
    else:
        path = source / filename
        if not path.exists():
            return []
        with open(path, encoding=encoding, errors="replace") as f:
            return list(csv.DictReader(f))


def batch_insert(conn, sql: str, rows: Iterator[tuple]) -> int:
    """Insert rows in batches; returns total row count inserted."""
    total = 0
    batch: list[tuple] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= BATCH_SIZE:
            conn.executemany(sql, batch)
            total += len(batch)
            batch.clear()
    if batch:
        conn.executemany(sql, batch)
        total += len(batch)
    return total
