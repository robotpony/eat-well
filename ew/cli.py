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
@click.option("--format", "fmt", default="console", type=click.Choice(["console", "md", "html"]), show_default=True, help="Output format")
@click.option("--output", "output_file", default=None, metavar="FILE", help="Write output to FILE instead of stdout")
def lookup(query, db, pick_n, per_grams, lang, fmt, output_file):
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

    if fmt == "md":
        from .markdown import render_label_md
        text = render_label_md(food, nutrients, portions, per_grams, lang)
        _write_output(text, output_file)
    elif fmt == "html":
        from .html import render_label_html
        text = render_label_html(food, nutrients, portions, per_grams, lang)
        _write_output(text, output_file)
    else:
        render_label(_console, food, nutrients, portions, per_grams, lang)


@cli.command()
@click.argument("ingredient")
@click.option("--db", default=None, metavar="PATH", help="Database path (default: ./work/ew.db)")
@click.option("--lang", default="en", type=click.Choice(["en", "fr"]), show_default=True, help="Search and display language")
def match(ingredient, db, lang):
    """Look up a single ingredient with quantity and show scaled nutrients.

    INGREDIENT is a quantity + food string, e.g. \"1 cup whole milk\" or \"100g almonds\".
    The best FTS match is selected automatically.
    """
    from .lookup import search, get_food, get_nutrients, get_portions, render_label
    from .parser import parse_ingredient, resolve_grams

    parsed = parse_ingredient(ingredient)
    if parsed is None:
        _console.print(
            "[red]Could not parse ingredient.[/red] "
            "Include a quantity, e.g. [bold]'1 cup whole milk'[/bold]."
        )
        raise SystemExit(1)

    db_p = _db_path(db)
    if not db_p.exists():
        _console.print(
            f"[red]Database not found at {db_p}. Run 'ew import' first.[/red]",
            err=True,
        )
        raise SystemExit(1)

    conn = connect(db_p)
    matches = search(conn, parsed.food_query, lang=lang, limit=1)
    if not matches:
        _console.print(f"[red]No match found for:[/red] {parsed.food_query}")
        raise SystemExit(1)

    food = get_food(conn, matches[0].id)
    portions = get_portions(conn, matches[0].id)
    grams, warning = resolve_grams(parsed.amount, parsed.unit, portions)

    if warning:
        _console.print(f"[yellow]⚠ {warning}[/yellow]")

    _console.print(
        f"\n[dim]{parsed.raw.strip()}[/dim]  [dim]→[/dim]  "
        f"[bold]{food['name_en']}[/bold]  [dim]{food['source_name']}  ({grams:g} g)[/dim]"
    )

    nutrients = get_nutrients(conn, matches[0].id)
    render_label(_console, food, nutrients, portions, per_grams=grams, lang=lang)


@cli.group()
def recipe():
    """Recipe evaluation tools."""


@recipe.command("eval")
@click.argument("file", type=click.File("r"), default="-")
@click.option("--db", default=None, metavar="PATH", help="Database path (default: ./work/ew.db)")
@click.option("--servings", default=None, type=click.IntRange(min=1), metavar="N", help="Show a per-serving column")
@click.option("--lang", default="en", type=click.Choice(["en", "fr"]), show_default=True, help="Search and display language")
@click.option("--format", "fmt", default="console", type=click.Choice(["console", "md", "html"]), show_default=True, help="Output format")
@click.option("--output", "output_file", default=None, metavar="FILE", help="Write output to FILE instead of stdout")
def recipe_eval(file, db, servings, lang, fmt, output_file):
    """Evaluate the nutrition of a recipe from an ingredient list.

    FILE is a text file with one ingredient per line (amount unit food).
    Use - to read from stdin. Lines starting with # and blank lines are ignored.

    \b
    Example file:
        1 cup whole milk
        2 large eggs
        1/2 cup rolled oats
        # optional notes are ignored
    """
    from .lookup import search, get_food, get_nutrients, get_portions
    from .parser import parse_ingredient, resolve_grams
    from .recipe import MatchResult, SkipResult, aggregate
    from rich.table import Table

    db_p = _db_path(db)
    if not db_p.exists():
        _console.print(
            f"[red]Database not found at {db_p}. Run 'ew import' first.[/red]",
            err=True,
        )
        raise SystemExit(1)

    conn = connect(db_p)

    # --- Parse and match each line ---
    results: list[MatchResult | SkipResult] = []
    for raw_line in file:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parsed = parse_ingredient(line)
        if parsed is None:
            results.append(SkipResult(line, "no quantity found"))
            continue

        top = search(conn, parsed.food_query, lang=lang, limit=1)
        if not top:
            results.append(SkipResult(line, "no food match"))
            continue

        food = get_food(conn, top[0].id)
        portions = get_portions(conn, top[0].id)
        grams, warning = resolve_grams(parsed.amount, parsed.unit, portions)
        nutrients = get_nutrients(conn, top[0].id, grams)
        results.append(MatchResult(
            raw=line,
            food_id=top[0].id,
            food_name=food["name_en"],
            source_name=food["source_name"],
            grams=grams,
            unit_warning=warning,
            nutrients=nutrients,
        ))

    if not results:
        _console.print("[dim]No ingredient lines found.[/dim]")
        return

    # --- Non-console output ---
    if fmt in ("md", "html"):
        matched_nc = [r for r in results if isinstance(r, MatchResult)]
        totals_nc = aggregate([r.nutrients for r in matched_nc])
        if fmt == "md":
            from .markdown import render_recipe_md
            text = render_recipe_md(results, totals_nc, servings)
        else:
            from .html import render_recipe_html
            text = render_recipe_html(results, totals_nc, servings)
        _write_output(text, output_file)
        return

    # --- Ingredient table ---
    _console.print()
    tbl = Table(box=None, show_header=False, padding=(0, 1), show_edge=False)
    tbl.add_column("icon",  no_wrap=True, width=2)
    tbl.add_column("input", no_wrap=True)
    tbl.add_column("arrow", no_wrap=True, style="dim")
    tbl.add_column("match", style="bold")
    tbl.add_column("grams", justify="right", style="green")
    tbl.add_column("note",  style="yellow dim")

    for r in results:
        if isinstance(r, MatchResult):
            icon = "[green]✓[/green]" if not r.unit_warning else "[yellow]⚠[/yellow]"
            tbl.add_row(
                icon,
                r.raw,
                "→",
                r.food_name,
                f"{r.grams:g} g",
                r.unit_warning or "",
            )
        else:
            tbl.add_row("[red]✗[/red]", r.raw, "", f"[dim]{r.reason}[/dim]", "", "")

    _console.print(tbl)

    # --- Aggregate ---
    matched = [r for r in results if isinstance(r, MatchResult)]
    if not matched:
        _console.print("\n[red]No ingredients matched.[/red]")
        return

    totals = aggregate([r.nutrients for r in matched])

    # --- Totals table ---
    _console.print()
    n_matched = len(matched)
    n_total = len(results)
    label = f"{n_matched} of {n_total} ingredient{'s' if n_total != 1 else ''} matched"
    _console.rule(f"[dim]{label}[/dim]", style="bright_black")
    _console.print()

    from .lookup import SECTIONS, fmt_value

    ttbl = Table(box=None, show_header=True, padding=(0, 2), show_edge=False)
    ttbl.add_column("", no_wrap=True, min_width=30)
    ttbl.add_column("Total", justify="right", style="green")
    has_servings = servings is not None
    if has_servings:
        ttbl.add_column(f"Per serving (÷{servings})", justify="right", style="cyan")

    # Bucket rows into sections
    buckets: dict[str, list] = {name: [] for name, *_ in SECTIONS}
    buckets["Other"] = []
    for row in totals:
        rank = row["rank"]
        placed = False
        for sname, lo, hi in SECTIONS:
            if lo <= rank <= hi:
                buckets[sname].append(row)
                placed = True
                break
        if not placed:
            buckets["Other"].append(row)

    def _trow(name: str, v1: str, v2: str) -> None:
        if has_servings:
            ttbl.add_row(name, v1, v2)
        else:
            ttbl.add_row(name, v1)

    first_section = True
    for sname, *_ in SECTIONS:
        rows = buckets[sname]
        if not rows:
            continue
        if not first_section:
            _trow("", "", "")
        first_section = False
        _trow(f"[bold]{sname}[/bold]", "", "")
        for n in rows:
            val = fmt_value(n["value"], n["unit"])
            per_srv = fmt_value(n["value"] / servings, n["unit"]) if has_servings else ""
            _trow(f"  {n['name_en']}", val, per_srv)

    _console.print(ttbl)
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


def _write_output(text: str, output_file: str | None) -> None:
    """Write *text* to *output_file*, or to stdout if output_file is None."""
    if output_file:
        Path(output_file).write_text(text, encoding="utf-8")
    else:
        click.echo(text, nl=False)


def _print_source(counts: dict[str, int]) -> None:
    labels = [("food", "foods"), ("food_portion", "portions"), ("food_category", "categories")]
    parts = [
        f"[green]{counts[key]:,}[/green] {label}"
        for key, label in labels
        if counts.get(key)
    ]
    if parts:
        _console.print("  " + "  [dim]·[/dim]  ".join(parts))
