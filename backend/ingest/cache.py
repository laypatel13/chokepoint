"""Tiny JSON disk cache so re-seeding never re-hits npm or OSV."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

CACHE_DIR = Path(os.getenv("CHOKEPOINT_CACHE", Path(__file__).resolve().parents[2] / ".cache" / "http"))


def _path(namespace: str, key: str) -> Path:
    digest = hashlib.sha256(key.encode()).hexdigest()[:32]
    return CACHE_DIR / namespace / f"{digest}.json"


def get(namespace: str, key: str) -> Any | None:
    p = _path(namespace, key)
    if p.exists():
        return json.loads(p.read_text())
    return None


def put(namespace: str, key: str, value: Any) -> None:
    p = _path(namespace, key)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(value))
    tmp.replace(p)
