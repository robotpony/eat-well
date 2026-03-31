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


def _work_dir(db_override: str | None) -> Path:
    return _db_path(db_override).parent


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

    db_p = _db_path(db)
    if not db_p.exists():
        _console.print(
            f"[red]Database not found at {db_p}. Run 'ew import' first.[/red]",
            err=True,
        )
        raise SystemExit(1)

    conn = connect(db_p)

    from .resolution import load_context
    ctx = load_context(conn, _work_dir(db))

    parsed = parse_ingredient(ingredient, aliases=ctx.aliases, taste_defaults=ctx.taste_defaults)
    if parsed is None:
        _console.print(
            "[red]Could not parse ingredient.[/red] "
            "Include a quantity, e.g. [bold]'1 cup whole milk'[/bold]."
        )
        raise SystemExit(1)

    matches = search(conn, parsed.food_query, lang=lang, limit=1)
    if not matches:
        _console.print(f"[red]No match found for:[/red] {parsed.food_query}")
        raise SystemExit(1)

    food = get_food(conn, matches[0].id)
    portions = get_portions(conn, matches[0].id)
    grams, warning = resolve_grams(parsed.amount, parsed.unit, portions, parsed.food_query, ctx.food_weights, ctx.user_cache)

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
@click.option("--servings", default=None, type=click.IntRange(min=1), metavar="N", help="Number of servings; sets per-portion column to total weight ÷ N")
@click.option("--portion", default=None, type=click.FloatRange(min=1), metavar="GRAMS", help="Per-portion gram weight for the second column (default: 150 g)")
@click.option("--lang", default="en", type=click.Choice(["en", "fr"]), show_default=True, help="Search and display language")
@click.option("--format", "fmt", default="console", type=click.Choice(["console", "md", "html"]), show_default=True, help="Output format")
@click.option("--output", "output_file", default=None, metavar="FILE", help="Write output to FILE instead of stdout")
@click.option("--interactive", "-i", is_flag=True, default=False, help="Prompt to resolve unmatched items and 1 g fallbacks")
def recipe_eval(file, db, servings, portion, lang, fmt, output_file, interactive):
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
    from .resolution import load_context
    from rich.table import Table

    db_p = _db_path(db)
    if not db_p.exists():
        _console.print(
            f"[red]Database not found at {db_p}. Run 'ew import' first.[/red]",
            err=True,
        )
        raise SystemExit(1)

    conn = connect(db_p)
    ctx = load_context(conn, _work_dir(db))

    # --- Parse and match each line ---
    results: list[MatchResult | SkipResult] = []
    parsed_for: list = []   # parallel: ParsedIngredient or None per result entry

    for raw_line in file:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parsed = parse_ingredient(line, aliases=ctx.aliases, taste_defaults=ctx.taste_defaults)
        if parsed is None:
            results.append(SkipResult(line, "no quantity found"))
            parsed_for.append(None)
            continue

        top = search(conn, parsed.food_query, lang=lang, limit=1)
        if not top:
            results.append(SkipResult(line, "no food match"))
            parsed_for.append(parsed)
            continue

        food = get_food(conn, top[0].id)
        portions = get_portions(conn, top[0].id)
        grams, warning = resolve_grams(
            parsed.amount, parsed.unit, portions,
            parsed.food_query, ctx.food_weights, ctx.user_cache,
        )
        # Prefer parser-level note (e.g. to-taste default) over gram-resolution warning
        display_warning = parsed.note or warning
        nutrients = get_nutrients(conn, top[0].id, grams)
        results.append(MatchResult(
            raw=line,
            food_id=top[0].id,
            food_name=food["name_en"],
            source_name=food["source_name"],
            grams=grams,
            unit_warning=display_warning,
            nutrients=nutrients,
        ))
        parsed_for.append(parsed)

    # --- Interactive resolution pass (P9c) ---
    if interactive:
        _interactive_pass(conn, results, parsed_for, ctx, lang)

    if not results:
        _console.print("[dim]No ingredient lines found.[/dim]")
        return

    # --- Aggregate (needed for portion calculation and non-console output) ---
    matched_all = [r for r in results if isinstance(r, MatchResult)]
    total_recipe_grams = sum(r.grams for r in matched_all)

    # --- Per-portion column parameters ---
    # --portion overrides --servings; both override the 150 g default.
    if portion is not None:
        portion_grams = float(portion)
        portion_col_label = f"Per {portion_grams:g} g"
    elif servings is not None and total_recipe_grams > 0:
        portion_grams = total_recipe_grams / servings
        portion_col_label = f"Per serving (÷{servings}, {portion_grams:.0f} g)"
    else:
        portion_grams = 150.0
        portion_col_label = "Per 150 g"

    portion_factor = portion_grams / total_recipe_grams if total_recipe_grams > 0 else 0.0

    # --- Non-console output ---
    if fmt in ("md", "html"):
        totals_nc = aggregate([r.nutrients for r in matched_all])
        if fmt == "md":
            from .markdown import render_recipe_md
            text = render_recipe_md(results, totals_nc, portion_col_label, portion_factor)
        else:
            from .html import render_recipe_html
            text = render_recipe_html(results, totals_nc, portion_col_label, portion_factor)
        _write_output(text, output_file)
        return

    # --- Ingredient table ---
    _console.print()
    tbl = Table(box=None, show_header=False, padding=(0, 1), show_edge=False)
    tbl.add_column("icon",  no_wrap=True, width=2)
    tbl.add_column("input", no_wrap=True, max_width=38, overflow="ellipsis")
    tbl.add_column("arrow", no_wrap=True, style="dim")
    tbl.add_column("match", no_wrap=True, max_width=30, overflow="ellipsis", style="bold")
    tbl.add_column("grams", justify="right", style="green", no_wrap=True)
    tbl.add_column("note",  style="yellow dim", max_width=28, overflow="fold")

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

    matched = matched_all
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
    ttbl.add_column(f"Total ({total_recipe_grams:,.0f} g)", justify="right", style="green")
    ttbl.add_column(portion_col_label, justify="right", style="cyan")

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

    first_section = True
    for sname, *_ in SECTIONS:
        rows = buckets[sname]
        if not rows:
            continue
        if not first_section:
            ttbl.add_row("", "", "")
        first_section = False
        ttbl.add_row(f"[bold]{sname}[/bold]", "", "")
        for n in rows:
            val = fmt_value(n["value"], n["unit"])
            per_portion = fmt_value(n["value"] * portion_factor, n["unit"])
            ttbl.add_row(f"  {n['name_en']}", val, per_portion)

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


# ---------------------------------------------------------------------------
# Management commands  (P9)
# ---------------------------------------------------------------------------

@cli.group()
def alias():
    """Manage food name aliases (e.g. msg → monosodium glutamate)."""


@alias.command("list")
@click.option("--db", default=None, metavar="PATH")
def alias_list(db):
    """Show all aliases: bundled defaults and user-defined overrides."""
    from .resolution import list_aliases
    from rich.table import Table

    db_p = _db_path(db)
    conn = connect(db_p) if db_p.exists() else None
    if conn is not None:
        create_schema(conn)
    bundled, user = list_aliases(conn)

    tbl = Table(box=None, show_header=True, padding=(0, 2), show_edge=False)
    tbl.add_column("Input", style="bold")
    tbl.add_column("Replacement")
    tbl.add_column("Source", style="dim")

    user_keys = {u["input_key"] for u in user}
    for key, rep in sorted(bundled.items()):
        if key not in user_keys:
            tbl.add_row(key, rep, "bundled")
    for u in user:
        tbl.add_row(u["input_key"], u["replacement"], "user")

    _console.print(tbl)


@alias.command("add")
@click.argument("key")
@click.argument("replacement")
@click.option("--db", default=None, metavar="PATH")
def alias_add(key, replacement, db):
    """Add or update a user alias.  KEY is the query text to replace."""
    from .resolution import save_alias
    db_p = _db_path(db)
    db_p.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_p)
    create_schema(conn)
    save_alias(conn, key, replacement)
    _console.print(f"[green]✓[/green]  [bold]{key}[/bold] → {replacement}")


# -----------

@cli.group()
def weights():
    """Manage the food weight reference table (food + unit → grams)."""


@weights.command("list")
@click.argument("food", default="", required=False)
@click.option("--db", default=None, metavar="PATH")
def weights_list(food, db):
    """Show food weight reference entries.  Filter by FOOD substring if given."""
    from .resolution import list_food_weights
    from rich.table import Table

    bundled, user = list_food_weights(_work_dir(db))

    tbl = Table(box=None, show_header=True, padding=(0, 2), show_edge=False)
    tbl.add_column("Food key", style="bold")
    tbl.add_column("Unit")
    tbl.add_column("Grams", justify="right")
    tbl.add_column("Note", style="dim")
    tbl.add_column("Source", style="dim")

    user_keys = {(u["key"].lower(), u["unit"].lower()) for u in user}

    def _add(entries, source):
        for e in entries:
            if food and food.lower() not in e["key"].lower():
                continue
            tbl.add_row(e["key"], e["unit"], str(e["grams"]), e.get("note", ""), source)

    _add([e for e in bundled if (e["key"].lower(), e["unit"].lower()) not in user_keys], "bundled")
    _add(user, "user")
    _console.print(tbl)


@weights.command("add")
@click.argument("food_key")
@click.argument("unit")
@click.argument("grams", type=float)
@click.option("--db", default=None, metavar="PATH")
def weights_add(food_key, unit, grams, db):
    """Add or update a food weight entry.

    FOOD_KEY is a substring of the food name (e.g. "shallot").
    UNIT is the portion unit (e.g. "each", "cup", "medium").
    GRAMS is the gram weight for one unit.
    """
    from .resolution import save_food_weight
    wd = _work_dir(db)
    wd.mkdir(parents=True, exist_ok=True)
    save_food_weight(wd, food_key, unit, grams)
    _console.print(f"[green]✓[/green]  {food_key} × 1 {unit} = {grams:g} g")


# -----------

@cli.group()
def portions():
    """Manage the interactive portion cache (resolved from recipe eval -i)."""


@portions.command("list")
@click.option("--db", default=None, metavar="PATH")
def portions_list(db):
    """Show all cached portion answers."""
    from .resolution import list_portion_cache
    from rich.table import Table

    db_p = _db_path(db)
    if not db_p.exists():
        _console.print("[dim]No database found — cache is empty.[/dim]")
        return

    conn = connect(db_p)
    create_schema(conn)
    entries = list_portion_cache(conn)

    if not entries:
        _console.print("[dim]Portion cache is empty.[/dim]")
        return

    tbl = Table(box=None, show_header=True, padding=(0, 2), show_edge=False)
    tbl.add_column("Food", style="bold")
    tbl.add_column("Unit")
    tbl.add_column("g / unit", justify="right")
    tbl.add_column("Saved", style="dim")
    for e in entries:
        tbl.add_row(e["food_query"], e["unit"] or "each", f"{e['gram_weight']:g}", e["created_at"][:10])
    _console.print(tbl)


@portions.command("clear")
@click.option("--db", default=None, metavar="PATH")
@click.confirmation_option(prompt="Clear the entire portion cache?")
def portions_clear(db):
    """Delete all entries from the interactive portion cache."""
    from .resolution import clear_portion_cache
    db_p = _db_path(db)
    if not db_p.exists():
        _console.print("[dim]No database found — nothing to clear.[/dim]")
        return
    conn = connect(db_p)
    create_schema(conn)
    clear_portion_cache(conn)
    _console.print("[green]✓[/green]  Portion cache cleared.")


# ---------------------------------------------------------------------------
# Interactive resolution helper  (P9c)
# ---------------------------------------------------------------------------

def _interactive_pass(conn, results, parsed_for, ctx, lang):
    """Prompt the user for no-match and 1 g-fallback items; update results in place."""
    from .lookup import search, get_food, get_nutrients, get_portions
    from .parser import parse_ingredient, resolve_grams
    from .recipe import MatchResult, SkipResult
    from .resolution import save_alias, save_portion_cache

    no_match_idx = [
        i for i, r in enumerate(results)
        if isinstance(r, SkipResult) and r.reason == "no food match"
    ]
    fallback_idx = [
        i for i, r in enumerate(results)
        if isinstance(r, MatchResult) and r.unit_warning and "1 g" in r.unit_warning
    ]

    if not no_match_idx and not fallback_idx:
        return

    _console.print()
    _console.rule("[dim]Interactive resolution[/dim]  [dim italic]Press Enter to skip[/dim italic]", style="bright_black")

    # No-match: ask for a better search term and save as alias
    for i in no_match_idx:
        r = results[i]
        p = parsed_for[i]
        food_key = p.food_query if p else r.raw.strip()
        _console.print(f"\n  [red]✗[/red]  No match for [bold]{food_key!r}[/bold]  [dim](from: {r.raw})[/dim]")
        replacement = click.prompt("  Better search term", default="", show_default=False)
        if not replacement.strip():
            continue
        save_alias(conn, food_key, replacement.strip())
        ctx.aliases[food_key.lower()] = replacement.strip()
        # Re-parse and re-search with updated aliases
        new_p = parse_ingredient(r.raw, aliases=ctx.aliases, taste_defaults=ctx.taste_defaults)
        if new_p:
            top = search(conn, new_p.food_query, lang=lang, limit=1)
            if top:
                food = get_food(conn, top[0].id)
                portions = get_portions(conn, top[0].id)
                grams, warning = resolve_grams(
                    new_p.amount, new_p.unit, portions,
                    new_p.food_query, ctx.food_weights, ctx.user_cache,
                )
                nutrients = get_nutrients(conn, top[0].id, grams)
                results[i] = MatchResult(
                    raw=r.raw, food_id=top[0].id, food_name=food["name_en"],
                    source_name=food["source_name"], grams=grams,
                    unit_warning=new_p.note or warning, nutrients=nutrients,
                )

    # 1 g fallbacks: ask for the gram weight per unit
    for i in fallback_idx:
        r = results[i]
        p = parsed_for[i]
        unit_label = (p.unit or "each") if p else "each"
        food_label = (p.food_query if p else r.food_name)
        _console.print(
            f"\n  [yellow]⚠[/yellow]  1 g fallback for [bold]{r.raw}[/bold]"
            f"  [dim](matched: {r.food_name})[/dim]"
        )
        gram_input = click.prompt(f"  Grams per {unit_label}", default="", show_default=False)
        if not gram_input.strip():
            continue
        try:
            grams_per_unit = float(gram_input.strip())
        except ValueError:
            _console.print("  [red]Not a number, skipped.[/red]")
            continue
        if p:
            save_portion_cache(conn, p.food_query, p.unit, grams_per_unit)
            ctx.user_cache[(p.food_query, p.unit)] = grams_per_unit
        new_grams = (p.amount if p else 1.0) * grams_per_unit
        new_nutrients = get_nutrients(conn, r.food_id, new_grams)
        results[i] = MatchResult(
            raw=r.raw, food_id=r.food_id, food_name=r.food_name,
            source_name=r.source_name, grams=new_grams,
            unit_warning=None, nutrients=new_nutrients,
        )


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

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
