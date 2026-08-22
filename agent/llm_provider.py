"""Local language-model configuration for JARVIS."""

from __future__ import annotations

import os
from urllib.error import URLError
from urllib.request import urlopen

from openai import AsyncOpenAI
from livekit.plugins import openai


def create_llm():
    """Use LiveKit's OpenAI-compatible adapter against local Ollama."""
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    client = AsyncOpenAI(
        base_url=base_url,
        api_key="ollama",
        timeout=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60")),
        max_retries=0,
    )
    return openai.LLM.with_ollama(
        model=os.getenv("AIOS_LLM_MODEL", "gemma4:e2b"),
        client=client,
    )


def check_ollama() -> None:
    """Fail early with a useful message when the local model server is absent."""
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1").rstrip("/")
    model = os.getenv("AIOS_LLM_MODEL", "gemma4:e2b")
    try:
        with urlopen(f"{base_url}/models", timeout=2) as response:
            if response.status != 200:
                raise RuntimeError(f"Ollama returned HTTP {response.status}")
    except (OSError, URLError) as exc:
        raise SystemExit(
            "Ollama is not reachable. Start it with `ollama serve`, then ensure "
            f"the model exists with `ollama pull {model}`."
        ) from exc
