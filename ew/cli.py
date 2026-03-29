"""CLI entry point for the ew tool."""

import os
from pathlib import Path

import click
from rich.console import Console
from rich.rule import Rule

from .db import connect, create_schema, rebuild_fts
from .importers.cnf import CnfImporter, SOURCE_NAME as _CNF_NAME
from .importers.usda import UsaImporter

_DEFAULT_DB = Path("work/ew.db")
_DEFAULT_IMPORT_DIR = Path("import")
_console = Console()


def _db_path(override: str | None) -> Path:
    return Path(override) if override else Path(os.environ.get("EW_DB", _DEFAULT_DB))


def _import_dir(override: str | None) -> Path:
    return Path(override) if override else Path(os.environ.get("EW_IMPORT_DIR", _DEFAULT_IMPORT_DIR))


@click.group()
def cli():
    """Eat Well + Win The Fridge — nutrition tool."""


@cli.command("import")
@click.option("--db", default=None, metavar="PATH", help="Database path (default: ./work/ew.db)")
@click.option("--import-dir", default=None, metavar="DIR", help="Import data root (default: ./import)")
def import_cmd(db, import_dir):
    """Import nutrition data from raw CSV files into the database.

    Reads CNF and USDA FoodData Central sources from the import/ directory.
    Safe to re-run: existing rows are kept, new rows are added.
    """
    db_p = _db_path(db)
    idir = _import_dir(import_dir)

    db_p.parent.mkdir(parents=True, exist_ok=True)
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

    _console.print()
    _console.rule("[bold]ew import[/bold]", style="bright_black")
    _console.print()

    cnf_dir = idir / "cad" / "cnf-fcen-csv"
    if cnf_dir.exists():
        _console.print(f"[bold]{_CNF_NAME}[/bold]")
        counts = CnfImporter(conn).run(cnf_dir)
        _print_source(counts)
    else:
        _console.print(f"[dim]{_CNF_NAME}  —  not found, skipped[/dim]")

    for path, _code, name, _version in _USDA_SOURCES:
        _console.print()
        if path.exists():
            _console.print(f"[bold]{name}[/bold]")
            counts = UsaImporter(conn).run(path, _code, name, _version)
            _print_source(counts)
        else:
            _console.print(f"[dim]{name}  —  not found, skipped[/dim]")

    _console.print()
    _console.print("[dim]Rebuilding search index…[/dim]", end=" ")
    rebuild_fts(conn)
    conn.commit()
    _console.print("[green]✓[/green]")

    total = conn.execute("SELECT COUNT(*) FROM food").fetchone()[0]
    _console.print()
    _console.rule(style="bright_black")
    _console.print(
        f"  [bold green]{total:,}[/bold green] foods indexed"
        f"  [dim]→[/dim]  [cyan]{db_p}[/cyan]"
    )
    _console.rule(style="bright_black")
    _console.print()


@cli.command()
@click.option("--db", default=None, metavar="PATH", help="Database path (default: ./work/ew.db)")
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

    from rich.table import Table

    table = Table(title="Data Sources", show_lines=False)
    table.add_column("Code", style="bold")
    table.add_column("Name")
    table.add_column("Version")
    table.add_column("Foods", justify="right")
    for row in rows:
        table.add_row(row["code"], row["name"], row["version"] or "—", f"{row['foods']:,}")
    _console.print(table)


def _print_source(counts: dict[str, int]) -> None:
    labels = [("food", "foods"), ("food_portion", "portions"), ("food_category", "categories")]
    parts = [
        f"[green]{counts[key]:,}[/green] {label}"
        for key, label in labels
        if counts.get(key)
    ]
    if parts:
        _console.print("  " + "  [dim]·[/dim]  ".join(parts))
