"""User settings for the CLI: which LLM to use (if any), watcher options, the hosted site.

- Settings live in <config dir>/config.toml (no secrets in it).
- API keys live in the OS keychain (macOS Keychain, Windows Credential Manager, Secret Service on Linux)
  via `keyring`; if no keychain is available, set CHOKEPOINT_LLM_API_KEY instead.
- Environment variables always win over the file, so CI and Docker can configure everything with env.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir

CONFIG_FILE = Path(os.getenv("CHOKEPOINT_CONFIG", Path(user_config_dir("chokepoint", appauthor=False)) / "config.toml"))
KEYRING_SERVICE = "chokepoint"

# OpenAI-compatible endpoints. `local` providers need no key. `effort`: accepts reasoning_effort=none.
PRESETS: dict[str, dict[str, Any]] = {
    "ollama":     {"label": "Ollama (local)",    "base_url": "http://localhost:11434/v1", "local": True, "effort": True},
    "lmstudio":   {"label": "LM Studio (local)", "base_url": "http://localhost:1234/v1",  "local": True, "effort": False},
    "llamacpp":   {"label": "llama.cpp server (local)", "base_url": "http://localhost:8080/v1", "local": True, "effort": False},
    "openai":     {"label": "OpenAI",     "base_url": "https://api.openai.com/v1",                              "local": False, "effort": False},
    "groq":       {"label": "Groq",       "base_url": "https://api.groq.com/openai/v1",                         "local": False, "effort": False},
    "gemini":     {"label": "Google Gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "local": False, "effort": False},
    "openrouter": {"label": "OpenRouter", "base_url": "https://openrouter.ai/api/v1",                           "local": False, "effort": False},
    "anthropic":  {"label": "Anthropic (OpenAI-compatible endpoint)", "base_url": "https://api.anthropic.com/v1/", "local": False, "effort": False},
}


def load() -> dict:
    try:
        return tomllib.loads(CONFIG_FILE.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _toml_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def save(data: dict) -> None:
    lines = ["# Chokepoint settings. API keys are NOT stored here (they're in your OS keychain).", ""]
    for section, values in data.items():
        if not isinstance(values, dict):
            continue
        lines.append(f"[{section}]")
        lines += [f"{k} = {_toml_value(v)}" for k, v in values.items() if v is not None]
        lines.append("")
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text("\n".join(lines))


def update(section: str, **values: Any) -> dict:
    data = load()
    data[section] = {**data.get(section, {}), **values}
    save(data)
    return data


def clear(section: str) -> None:
    data = load()
    data.pop(section, None)
    save(data)


# ---------- API keys ---------------------------------------------------------------------


def set_key(provider: str, key: str) -> bool:
    """Store a key in the OS keychain. Returns False when no keychain is available."""
    try:
        import keyring

        keyring.set_password(KEYRING_SERVICE, provider, key)
        return True
    except Exception:
        return False


def get_key(provider: str) -> str | None:
    if os.getenv("CHOKEPOINT_LLM_API_KEY"):
        return os.getenv("CHOKEPOINT_LLM_API_KEY")
    try:
        import keyring

        return keyring.get_password(KEYRING_SERVICE, provider)
    except Exception:
        return None


def delete_key(provider: str) -> None:
    try:
        import keyring

        keyring.delete_password(KEYRING_SERVICE, provider)
    except Exception:
        pass


# ---------- apply to the process ---------------------------------------------------------


def apply_llm_env() -> None:
    """Expose the configured LLM through the env vars chokepoint.agent.llm reads.
    Anything already set in the environment wins (CI, Docker, a one-off override)."""
    llm = load().get("llm", {})
    if not llm or llm.get("provider") == "off" or os.getenv("LLM_BASE_URL"):
        return
    provider = llm.get("provider", "custom")
    os.environ.setdefault("LLM_BASE_URL", llm.get("base_url", ""))
    os.environ.setdefault("LLM_MODEL", llm.get("model", ""))
    key = get_key(provider)
    if key:
        os.environ.setdefault("LLM_API_KEY", key)
    if llm.get("reasoning_effort"):
        os.environ.setdefault("LLM_REASONING_EFFORT", llm["reasoning_effort"])


# ---- GitHub: where Nightjar and `fix --pr` open fix PRs (your repo, your fine-grained token) ----

PRS_PER_DAY = 5  # Nightjar opens at most this many new PRs a day, whatever happens


def github() -> dict:
    """Where fix PRs go: {repo, path (of package.json in the repo), project (the one app this repo belongs to),
    token}. The token: CHOKEPOINT_GITHUB_TOKEN, else the keychain. Never the LLM key: get_key's
    CHOKEPOINT_LLM_API_KEY shortcut is for LLM providers only, and must not be sent to GitHub."""
    cfg = load().get("github", {})
    token = os.getenv("CHOKEPOINT_GITHUB_TOKEN") or _keychain("github")
    return {"repo": cfg.get("repo") or None, "path": cfg.get("path") or "", "project": cfg.get("project") or None,
            "token": token or None}


def _keychain(name: str) -> str | None:
    try:
        import keyring

        return keyring.get_password(KEYRING_SERVICE, name)
    except Exception:
        return None
