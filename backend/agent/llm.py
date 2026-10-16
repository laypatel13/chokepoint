"""OpenAI-compatible LLM client. Provider chosen by env (Ollama locally, Groq/Gemini when deployed)."""

from __future__ import annotations

import ipaddress
import os
import re
from urllib.parse import urlparse

from openai import OpenAI


def model() -> str | None:
    return os.getenv("LLM_MODEL") or None


def base_url() -> str | None:
    url = os.getenv("LLM_BASE_URL")
    # Inside docker compose, "localhost" is the container; reach Ollama on the host instead.
    if url and os.path.exists("/.dockerenv"):
        url = url.replace("localhost", "host.docker.internal").replace("127.0.0.1", "host.docker.internal")
    return url


def insecure(url: str | None) -> str | None:
    """Why `url` mustn't carry an API key, or None. Plain http only on this machine or your own network
    (Ollama, LM Studio); anything else would send the key unencrypted across the internet."""
    if not url:
        return None
    u = urlparse(url)
    if u.scheme == "https":
        return None
    if u.scheme != "http":
        return f"LLM_BASE_URL must start with https:// (got {u.scheme or 'no scheme'})"
    host = (u.hostname or "").lower()
    if host in ("localhost", "host.docker.internal") or host.endswith((".local", ".localhost", ".internal")):
        return None
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_loopback or ip.is_private or ip.is_link_local:
            return None
    except ValueError:
        pass
    return f"plain http to {host} would send your API key unencrypted: use https://"


# Shapes of the secrets users give Chokepoint (OpenAI/Anthropic/Groq/OpenRouter/Gemini keys, GitHub tokens).
_SECRET = re.compile(r"(sk-[A-Za-z0-9_\-]{8,}|gsk_[A-Za-z0-9]{8,}|AIza[0-9A-Za-z_\-]{20,}|"
                     r"github_pat_[A-Za-z0-9_]{8,}|gh[pousr]_[A-Za-z0-9]{8,}|xox[abp]-[A-Za-z0-9-]{8,})")


def redact(text: str) -> str:
    """Error text that is safe to show or log: the configured key, and anything shaped like a key, removed.
    Providers sometimes echo part of a rejected key back in their error message."""
    for secret in (os.getenv("LLM_API_KEY"), os.getenv("CHOKEPOINT_GITHUB_TOKEN"), os.getenv("GITHUB_TOKEN")):
        if secret and len(secret) >= 8:
            text = text.replace(secret, "***")
    return _SECRET.sub("***", text)


def error_text(e: Exception, limit: int = 200) -> str:
    return redact(f"{type(e).__name__}: {e}")[:limit]


def client() -> OpenAI | None:
    if not base_url() or not model() or insecure(base_url()):
        return None
    return OpenAI(
        base_url=base_url(),
        api_key=os.getenv("LLM_API_KEY") or "none",
        timeout=float(os.getenv("LLM_TIMEOUT", "60")),
        max_retries=0,
    )


def extra() -> dict:
    """Optional provider knobs. LLM_REASONING_EFFORT=none turns off 'thinking' on models that
    support it (much faster on local Ollama); leave unset for providers that reject it."""
    effort = os.getenv("LLM_REASONING_EFFORT")
    return {"reasoning_effort": effort} if effort else {}
