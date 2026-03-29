"""CLI entry point for the ew tool."""

import os
from pathlib import Path

import click

from .db import connect, create_schema, rebuild_fts
from .importers.cnf import CnfImporter
from .importers.usda import UsaImporter

_DEFAULT_DB = Path("ew.db")
_DEFAULT_IMPORT_DIR = Path("import")


def _db_path(override: str | None) -> Path:
    return Path(override) if override else Path(os.environ.get("EW_DB", _DEFAULT_DB))


def _import_dir(override: str | None) -> Path:
    return Path(override) if override else Path(os.environ.get("EW_IMPORT_DIR", _DEFAULT_IMPORT_DIR))


@click.group()
def cli():
    """Eat Well + Win The Fridge — nutrition tool."""


@cli.command("import")
@click.option("--db", default=None, metavar="PATH", help="Database path (default: ./ew.db)")
@click.option("--import-dir", default=None, metavar="DIR", help="Import data root (default: ./import)")
def import_cmd(db, import_dir):
    """Import nutrition data from raw CSV files into the database.

    Reads CNF and USDA FoodData Central sources from the import/ directory.
    Safe to re-run: existing rows are kept, new rows are added.
    """
    db_p = _db_path(db)
    idir = _import_dir(import_dir)

    conn = connect(db_p)
    create_schema(conn)

    _USDA_SOURCES = [
        (
            idir / "usa" / "FoodData_Central_foundation_food_csv_2023-04-20",
            "usda_foundation",
            "USDA FoodData Central — Foundation Foods",
            "2023-04-20",
        ),
        (
            idir / "usa" / "FoodData_Central_sr_legacy_food_csv_2018-04.zip",
            "usda_sr_legacy",
            "USDA FoodData Central — SR Legacy",
            "2018-04",
        ),
        (
            idir / "usa" / "FoodData_Central_survey_food_csv_2022-10-28.zip",
            "usda_survey",
            "USDA FoodData Central — Survey (FNDDS)",
            "2022-10-28",
        ),
    ]

    cnf_dir = idir / "cad" / "cnf-fcen-csv"
    if cnf_dir.exists():
        click.echo("Importing CNF…")
        counts = CnfImporter(conn).run(cnf_dir)
        _print_counts("cnf", counts)
    else:
        click.echo(f"Skipping CNF (not found: {cnf_dir})")

    for path, code, name, version in _USDA_SOURCES:
        if path.exists():
            click.echo(f"Importing {code}…")
            counts = UsaImporter(conn).run(path, code, name, version)
            _print_counts(code, counts)
        else:
            click.echo(f"Skipping {code} (not found: {path})")

    click.echo("Rebuilding full-text search index…")
    rebuild_fts(conn)
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM food").fetchone()[0]
    click.echo(f"Done. {total:,} foods indexed in {db_p}.")


@cli.command()
@click.option("--db", default=None, metavar="PATH", help="Database path (default: ./ew.db)")
def sources(db):
    """List loaded data sources and food counts."""
    db_p = _db_path(db)
    if not db_p.exists():
        click.echo(f"Database not found at {db_p}. Run 'ew import' first.", err=True)
        raise SystemExit(1)

    conn = connect(db_p)
    rows = conn.execute(
        "SELECT s.code, s.name, s.version, COUNT(f.id) AS foods "
        "FROM source s LEFT JOIN food f ON f.source_id = s.id "
        "GROUP BY s.id ORDER BY s.id"
    ).fetchall()

    if not rows:
        click.echo("No sources loaded.")
        return

    try:
        from rich.table import Table
        from rich.console import Console

        table = Table(title="Data Sources", show_lines=False)
        table.add_column("Code", style="bold")
        table.add_column("Name")
        table.add_column("Version")
        table.add_column("Foods", justify="right")
        for row in rows:
            table.add_row(row["code"], row["name"], row["version"] or "—", f"{row['foods']:,}")
        Console().print(table)
    except ImportError:
        # Fallback if rich not installed
        click.echo(f"{'Code':<20} {'Version':<12} {'Foods':>8}  Name")
        for row in rows:
            click.echo(f"{row['code']:<20} {row['version'] or '—':<12} {row['foods']:>8}  {row['name']}")


def _print_counts(label: str, counts: dict[str, int]) -> None:
    parts = ", ".join(f"{v:,} {k}" for k, v in counts.items() if v)
    click.echo(f"  {label}: {parts}")
