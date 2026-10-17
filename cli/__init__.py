"""Chokepoint in your terminal: `chokepoint --help`.

Everything runs on your machine: an embedded FalkorDB (no Docker needed on Python 3.12+), npm and
OSV lookups, and only the LLM you configure. Environment is set up here, before any other
chokepoint module reads it.
"""

from __future__ import annotations

import importlib.util
import os
import sys

from platformdirs import user_cache_dir, user_data_dir

# CHOKEPOINT_DATA_DIR / CHOKEPOINT_CACHE_DIR move everything elsewhere (tests, several setups side by side).
DATA_DIR = os.getenv("CHOKEPOINT_DATA_DIR") or user_data_dir("chokepoint", appauthor=False)
CACHE_DIR = os.getenv("CHOKEPOINT_CACHE_DIR") or user_cache_dir("chokepoint", appauthor=False)


def _setup_environment() -> None:
    has_embedded = importlib.util.find_spec("redislite") is not None
    os.environ.setdefault("CHOKEPOINT_BACKEND", "embedded" if has_embedded else "server")
    os.environ.setdefault("CHOKEPOINT_DB", os.path.join(DATA_DIR, "graph.db"))
    os.environ.setdefault("CHOKEPOINT_CACHE", os.path.join(CACHE_DIR, "http"))


def main() -> None:
    _setup_environment()
    from chokepoint.cli import config

    config.apply_llm_env()  # your LLM settings (setup / config llm); env vars still win
    from chokepoint.cli.app import app  # imported after the environment is ready

    import typer
    from typer import rich_utils
    try:
        from typer._click import exceptions as cx  # newer Typer bundles its own click
    except ImportError:
        from click import exceptions as cx  # older Typer uses the click package

    # Not standalone, so usage errors come back to us and a missing argument gets a real hint. The rest is
    # what standalone mode does: Typer's own error box, "Aborted!", the exit code.
    try:
        code = app(prog_name="chokepoint", standalone_mode=False)
    except cx.MissingParameter as e:
        _missing(e)
    except cx.ClickException as e:
        rich_utils.rich_format_error(e)
        sys.exit(e.exit_code)
    except typer.Abort:
        rich_utils.rich_abort_error()
        sys.exit(1)
    sys.exit(code if isinstance(code, int) else 0)


def _missing(e) -> None:
    """`chokepoint check` with nothing after it: say what goes there, with the example from its help."""
    from chokepoint.cli import render as R

    ctx, param = e.ctx, e.param
    command = ctx.command_path if ctx else "chokepoint"
    what = (param.metavar or param.name or "an argument") if param else "an argument"
    example = (getattr(param, "help", "") or "").split("e.g. ", 1)
    R.err.print(f"[bold red]error[/] [bold]{command}[/] needs {what}.")
    if len(example) == 2:
        R.err.print(f"  for example: [cyan]{command} {example[1]}[/]")
    R.err.print(f"  [dim]more: {command} --help[/]")
    sys.exit(2)
