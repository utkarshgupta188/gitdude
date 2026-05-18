"""
ai.py — Unified AI provider wrapper for GitDude.

Single public function: ask_ai(prompt: str) -> str
Supports: gemini, groq, ollama, openai
"""

from __future__ import annotations

import sys
from typing import Optional, Iterator

from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner

from gitdude.config import (
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

def _ask_gemini(prompt: str, model: str, api_key: str, stream: bool = False) -> str | Iterator[str]:
    try:
        import google.generativeai as genai  # type: ignore
    except ImportError:
        raise RuntimeError(
            "google-generativeai is not installed. Run: pip install google-generativeai"
        )
    genai.configure(api_key=api_key)
    client = genai.GenerativeModel(model)
    
    if stream:
        response = client.generate_content(prompt, stream=True)
        def _gen():
            for chunk in response:
                try:
                    if chunk.text:
                        yield chunk.text
                except ValueError:
                    yield "[Response blocked by safety filters]"
        return _gen()
    else:
        response = client.generate_content(prompt)
        try:
            return response.text.strip()
        except ValueError:
            return "[Response blocked by safety filters]"


def _ask_groq(prompt: str, model: str, api_key: str, stream: bool = False) -> str | Iterator[str]:
    try:
        from groq import Groq  # type: ignore
    except ImportError:
        raise RuntimeError("groq is not installed. Run: pip install groq")
    client = Groq(api_key=api_key, timeout=20.0)
    
    if stream:
        completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            stream=True,
        )
        def _gen():
            for chunk in completion:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        return _gen()
    else:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=model,
        )
        content = chat_completion.choices[0].message.content
        return content.strip() if content else ""


def _ask_ollama(prompt: str, model: str, stream: bool = False) -> str | Iterator[str]:
    try:
        import ollama  # type: ignore
    except ImportError:
        raise RuntimeError("ollama is not installed. Run: pip install ollama")
    
    if stream:
        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        def _gen():
            for chunk in response:
                content = chunk.get("message", {}).get("content", "")  # type: ignore
                if content:
                    yield content
        return _gen()
    else:
        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        content = response.get("message", {}).get("content", "")
        return content.strip()


def _ask_openai(prompt: str, model: str, api_key: str, stream: bool = False) -> str | Iterator[str]:
    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        raise RuntimeError("openai is not installed. Run: pip install openai")
    client = OpenAI(api_key=api_key, timeout=20.0)
    
    if stream:
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        def _gen():
            for chunk in completion:
                content = chunk.choices[0].delta.content  # type: ignore
                if content:
                    yield content
        return _gen()
    else:
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        content = completion.choices[0].message.content
        return content.strip() if content else ""


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def _is_internet_available() -> bool:
    """Check if internet connection is available by pinging Google DNS."""
    import socket
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=1.5)
        return True
    except OSError:
        return False


def ask_ai(prompt: str, spinner_msg: str = "🤖 Thinking...", stream: bool = False) -> str:
    """
    Send a prompt to the configured AI provider and return the response.
    Shows a Rich spinner while waiting.
    Raises SystemExit on unrecoverable errors.
    """
    from gitdude.utils import error_panel  # late import to avoid circular

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

    LOCAL_PROVIDERS = {"ollama"}
    is_online = [True]
    net_thread = None

    if provider not in LOCAL_PROVIDERS:
        if not api_key:
            error_panel(
                f"No API key found for provider [bold]{provider}[/bold].\n"
                f"Run [bold cyan]gitdude config[/bold cyan] to set your key.",
                title="❌ Missing API Key",
            )
            sys.exit(1)
            
        # Run internet check in background
        import threading
        def _check_net():
            is_online[0] = _is_internet_available()
        net_thread = threading.Thread(target=_check_net, daemon=True)
        net_thread.start()

    try:
        if stream:
            with _spinner_context(spinner_msg):
                if provider == "gemini":
                    res = _ask_gemini(prompt, model, api_key, stream=True)
                elif provider == "groq":
                    res = _ask_groq(prompt, model, api_key, stream=True)
                elif provider == "openai":
                    res = _ask_openai(prompt, model, api_key, stream=True)
                elif provider == "ollama":
                    res = _ask_ollama(prompt, model, stream=True)
                else:
                    raise RuntimeError(f"Unknown provider: {provider}")
                
                if isinstance(res, str):
                    return res
                
                iterator = res
                try:
                    first_chunk = next(iterator)
                except StopIteration:
                    return ""
            
            console.print(first_chunk, end="")
            full_text = first_chunk
            
            for chunk in iterator:
                console.print(chunk, end="")
                full_text += chunk
            console.print()
            return full_text
        else:
            with _spinner_context(spinner_msg):
                if provider == "gemini":
                    result = _ask_gemini(prompt, model, api_key, stream=False)
                elif provider == "groq":
                    result = _ask_groq(prompt, model, api_key, stream=False)
                elif provider == "openai":
                    result = _ask_openai(prompt, model, api_key, stream=False)
                elif provider == "ollama":
                    result = _ask_ollama(prompt, model, stream=False)
                else:
                    raise RuntimeError(f"Unknown provider: {provider}")
            
            if isinstance(result, str):
                return result
            raise RuntimeError("Expected string response from AI provider")
            
    except RuntimeError as exc:
        error_panel(str(exc), title="❌ AI Provider Error")
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        # Wait for network check to finish if it was started
        if net_thread:
            net_thread.join(timeout=2.0)
            if not is_online[0]:
                error_panel(
                    "No internet connection detected.\n"
                    "Please check your network connection and try again.",
                    title="❌ No Internet Connection",
                )
                sys.exit(1)

        error_panel(
            f"An error occurred while calling [bold]{provider}[/bold]:\n{exc}\n\n"
            "Check your API key, network connection, and model name.",
            title="❌ AI Call Failed",
        )
        sys.exit(1)
