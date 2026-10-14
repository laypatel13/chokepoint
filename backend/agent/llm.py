"""OpenAI-compatible LLM client. Provider chosen by env (Ollama locally, Groq/Gemini when deployed)."""

from __future__ import annotations

import os

from openai import OpenAI


def model() -> str | None:
    return os.getenv("LLM_MODEL") or None


def base_url() -> str | None:
    url = os.getenv("LLM_BASE_URL")
    # Inside docker compose, "localhost" is the container; reach Ollama on the host instead.
    if url and os.path.exists("/.dockerenv"):
        url = url.replace("localhost", "host.docker.internal").replace("127.0.0.1", "host.docker.internal")
    return url


def client() -> OpenAI | None:
    if not base_url() or not model():
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
