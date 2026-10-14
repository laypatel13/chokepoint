"""Chokepoint in your terminal: `chokepoint --help`.

Everything runs on your machine: an embedded FalkorDB (no Docker needed on Python 3.12+), npm and
OSV lookups, and only the LLM you configure. Environment is set up here, before any other
chokepoint module reads it.
"""

from __future__ import annotations

import importlib.util
import os

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

    app()
