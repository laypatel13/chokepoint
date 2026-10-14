"""How Nightjar looks: a small pixel bird whose face shows its state (see nightjar.json).

The same drawing is used by the website; here it is drawn in the terminal with half-block
characters (one character = two pixels stacked), in the bird's real colours."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources

from rich.style import Style
from rich.text import Text

STATES = ("watching", "resting", "watch", "alert", "calm")


@lru_cache(maxsize=1)
def sprite() -> dict:
    return json.loads(resources.files("chokepoint.watch").joinpath("nightjar.json").read_text("utf-8"))


def state_for(level: str | None) -> str:
    """Nightjar's face for an event level: INFO/None → watching, WATCH → suspicious, ALERT → alarmed,
    CONFIRMED → alarmed (it was right), FIXED/OK → calm."""
    return {"WATCH": "watch", "ALERT": "alert", "CONFIRMED": "alert", "FIXED": "calm", "OK": "calm",
            "RESTING": "resting"}.get((level or "").upper(), "watching")


def frame(state: str) -> list[str]:
    """The pixel rows for one state: the shared body, that state's eyes, and its accent marks."""
    s = sprite()
    rows = [list(r) for r in s["body"]]
    for i, r in enumerate(s["eyes"][state]):
        rows[s["eyes_row"] + i] = list(r)
    for y, x in s["marks"].get(state, []):
        rows[y][x] = "a"
    return ["".join(r) for r in rows]


def _color(ch: str, state: str) -> str | None:
    s = sprite()
    return s["accent"][state] if ch == "a" else s["palette"].get(ch)


def bird(state: str = "watching") -> list[Text]:
    """The bird as terminal lines: each character is two pixels (top in the foreground colour of
    '▀', bottom in its background), so 14 pixel rows become 7 lines."""
    rows = frame(state)
    lines: list[Text] = []
    for y in range(0, len(rows), 2):
        line = Text()
        for x in range(len(rows[y])):
            top = _color(rows[y][x], state)
            bottom = _color(rows[y + 1][x], state) if y + 1 < len(rows) else None
            if top and bottom:
                line.append("▀", Style(color=top, bgcolor=bottom))
            elif top:
                line.append("▀", Style(color=top))
            elif bottom:
                line.append("▄", Style(color=bottom))
            else:
                line.append(" ")
        lines.append(line)
    return lines


def face(state: str = "watching") -> Text:
    """The one-line face used in front of log lines, in the state's colour."""
    return Text(sprite()["faces"][state], style=Style(color=sprite()["accent"][state], bold=state == "alert"))


def beside(state: str, text_lines: list[Text | str]) -> Text:
    """The bird with a few lines of text to its right (a banner)."""
    art = bird(state)
    out = Text()
    for i in range(max(len(art), len(text_lines))):
        out.append_text(art[i] if i < len(art) else Text(" " * 18))
        if i < len(text_lines):
            out.append("   ")
            t = text_lines[i]
            out.append_text(t if isinstance(t, Text) else Text.from_markup(t))
        out.append("\n")
    return out
