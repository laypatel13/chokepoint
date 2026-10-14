"""Deterministic question -> tool router. Used when no LLM is configured or the LLM fails,
so the core demo works with zero LLM calls."""

from __future__ import annotations

import re

KEY_RE = re.compile(r"(@?[a-z0-9][\w.\-]*(?:/[\w.\-]+)?)@(\d+\.\d+\.\d+[\w.\-+]*)", re.I)
USER_RE = re.compile(r"(?:if|account|maintainer|user)\s+@?([a-z0-9][\w.\-]*)\s+(?:gets?|is|was|were)\b", re.I)


def route(question: str) -> tuple[str, dict]:
    q = question.lower()
    m = KEY_RE.search(question)
    key = f"{m.group(1)}@{m.group(2)}" if m else None

    if key:
        if re.search(r"investigat|everything|full (check|report|picture)|all about", q):
            return "investigate", {"key": key}
        if re.search(r"lockfile|saved|fresh install|npm install|window", q):
            return "lockfile_saved_you", {"key": key}
        if re.search(r"\b(safe|fix|pin|upgrade|patch|override)\b", q):
            return "safe_version", {"key": key}
        if re.search(r"blast|radius|how many|depend on|depends on|who uses", q):
            return "blast_radius", {"key": key}
        return "explain_path", {"key": key}
    if re.search(r"nightjar|alert|watch(er|ed|ing)?\b|flagged|while i was|recall|remember", q):
        return "recall", {}
    if re.search(r"sept(ember)?\.? ?8|9/8|8 sep|2025 (attack|compromise|incident)|what happened", q):
        return "incident", {}
    v = re.search(r"(?:versions? of|which)\s+(@?[a-z0-9][\w.\-]*(?:/[\w.\-]+)?)\b(?:\s+(?:do|are|is|have))", q)
    if v and "version" in q:
        return "installed_versions", {"name": v.group(1)}
    if re.search(r"who|maintainer|poison|phish|account|chokepoint|take ?over|hijack|single point", q):
        u = USER_RE.search(question)
        return "chokepoints", ({"maintainer": u.group(1)} if u else {})
    if re.search(r"advisor|vulnerab|cve|ghsa|malware|malicious|known", q):
        return "known_advisories", {}
    return "graph_stats", {}
