"""
ai.py — Unified AI provider wrapper for GitDude.

Single public function: ask_ai(prompt: str) -> str
Supports: gemini, groq, ollama, openai
"""

from __future__ import annotations

import sys
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner

from gitwise.config import (
    get_config,
    get_current_provider,
    get_model_for_provider,
    get_provider_api_key,
    is_configured,
)

console = Console()


def _spinner_context(message: str = "🤖 Thinking..."):
    """Return a Rich Live context showing a spinner."""
    return Live(Spinner("dots", text=f"[bold magenta]{message}[/bold magenta]"), console=console, transient=True)


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------

def _ask_gemini(prompt: str, model: str, api_key: str) -> str:
    try:
        import google.generativeai as genai  # type: ignore
    except ImportError:
        raise RuntimeError(
            "google-generativeai is not installed. Run: pip install google-generativeai"
        )
    genai.configure(api_key=api_key)
    client = genai.GenerativeModel(model)
    response = client.generate_content(prompt)
    return response.text.strip()


def _ask_groq(prompt: str, model: str, api_key: str) -> str:
    try:
        from groq import Groq  # type: ignore
    except ImportError:
        raise RuntimeError("groq is not installed. Run: pip install groq")
    client = Groq(api_key=api_key)
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model=model,
    )
    return chat_completion.choices[0].message.content.strip()


def _ask_ollama(prompt: str, model: str, **_kwargs) -> str:
    try:
        import ollama  # type: ignore
    except ImportError:
        raise RuntimeError("ollama is not installed. Run: pip install ollama")
    response = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return response["message"]["content"].strip()


def _ask_openai(prompt: str, model: str, api_key: str) -> str:
    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        raise RuntimeError("openai is not installed. Run: pip install openai")
    client = OpenAI(api_key=api_key)
    completion = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return completion.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def ask_ai(prompt: str, spinner_msg: str = "🤖 Thinking...") -> str:
    """
    Send a prompt to the configured AI provider and return the response.
    Shows a Rich spinner while waiting.
    Raises SystemExit on unrecoverable errors.
    """
    from gitwise.utils import error_panel  # late import to avoid circular

    if not is_configured():
        error_panel(
            "GitDude is not configured yet.\nRun [bold cyan]gitdude config[/bold cyan] to get started.",
            title="❌ Not Configured",
        )
        sys.exit(1)

    cfg = get_config()
    provider = get_current_provider()
    model = get_model_for_provider(provider)
    api_key = get_provider_api_key(provider)

    if provider != "ollama" and not api_key:
        error_panel(
            f"No API key found for provider [bold]{provider}[/bold].\n"
            f"Run [bold cyan]gitdude config[/bold cyan] to set your key.",
            title="❌ Missing API Key",
        )
        sys.exit(1)

    provider_fn = {
        "gemini": _ask_gemini,
        "groq": _ask_groq,
        "ollama": _ask_ollama,
        "openai": _ask_openai,
    }.get(provider)

    if provider_fn is None:
        error_panel(
            f"Unknown provider: [bold]{provider}[/bold]\n"
            f"Run [bold cyan]gitdude config[/bold cyan] to choose a valid provider.",
            title="❌ Invalid Provider",
        )
        sys.exit(1)

    try:
        with _spinner_context(spinner_msg):
            result = provider_fn(prompt=prompt, model=model, api_key=api_key)
        return result
    except RuntimeError as exc:
        error_panel(str(exc), title="❌ AI Provider Error")
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        error_panel(
            f"An error occurred while calling [bold]{provider}[/bold]:\n{exc}\n\n"
            "Check your API key, network connection, and model name.",
            title="❌ AI Call Failed",
        )
        sys.exit(1)
