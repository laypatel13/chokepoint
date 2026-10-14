"""Facts about npm accounts that every front end shows the same way."""

from __future__ import annotations

# Automated or organisation accounts. Still ranked (a stolen bot token is as dangerous as a
# stolen password), just labelled so nobody mistakes them for a person.
KNOWN_BOTS = {"types", "npm-cli-ops", "renovate-bot", "dependabot", "semantic-release-bot", "greenkeeper"}


def is_bot(username: str) -> bool:
    u = username.lower()
    return u in KNOWN_BOTS or u.endswith(("-bot", "_bot", ".bot", "[bot]"))


def handle(username: str) -> str:
    """How a real account is written everywhere: @username."""
    return f"@{username}"
