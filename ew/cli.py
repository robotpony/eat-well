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
@click.argument("query")
@click.option("--db", default=None, metavar="PATH", help="Database path (default: ./work/ew.db)")
@click.option("--pick", "pick_n", default=None, type=int, metavar="N", help="Auto-select match N without prompting")
@click.option("--per", "per_grams", default=None, type=float, metavar="GRAMS", help="Second column: per N grams (default: first portion)")
@click.option("--lang", default="en", type=click.Choice(["en", "fr"]), show_default=True, help="Search and display language")
def lookup(query, db, pick_n, per_grams, lang):
    """Look up nutrition information for a food.

    QUERY is a plain-text search string, e.g. \"raw almonds\" or \"whole milk\".
    """
    from .lookup import search, get_food, get_nutrients, get_portions, render_label

    if per_grams is not None and per_grams <= 0:
        _console.print("[red]--per must be a positive number of grams.[/red]", err=True)
        raise SystemExit(1)

    db_p = _db_path(db)
    if not db_p.exists():
        _console.print(
            f"[red]Database not found at {db_p}. Run 'ew import' first.[/red]",
            err=True,
        )
        raise SystemExit(1)

    conn = connect(db_p)
    matches = search(conn, query, lang=lang)

    if not matches:
        _console.print(f"[red]No matches found for:[/red] {query}")
        raise SystemExit(1)

    # Resolve which match to display
    if pick_n is not None:
        if not (1 <= pick_n <= len(matches)):
            _console.print(
                f"[red]--pick {pick_n} is out of range (1–{len(matches)}).[/red]",
                err=True,
            )
            raise SystemExit(1)
        food_id = matches[pick_n - 1].id
    elif len(matches) == 1:
        food_id = matches[0].id
    else:
        _console.print()
        for i, m in enumerate(matches, 1):
            _console.print(f"  [bold]{i}[/bold]  {m.name}  [dim]{m.source_name}[/dim]")
        _console.print()
        choice = click.prompt("Pick", type=click.IntRange(1, len(matches)))
        food_id = matches[choice - 1].id

    food = get_food(conn, food_id)
    if food is None:
        _console.print("[red]Food not found.[/red]", err=True)
        raise SystemExit(1)

    nutrients = get_nutrients(conn, food_id)
    portions = get_portions(conn, food_id)
    render_label(_console, food, nutrients, portions, per_grams, lang)


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
