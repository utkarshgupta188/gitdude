"""
config.py — GitDude configuration management.
Stores config in ~/.gitdude/config.json.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".gitdude"
CONFIG_FILE = CONFIG_DIR / "config.json"

PROVIDERS = ["groq", "gemini", "ollama", "openai"]

DEFAULTS: dict[str, Any] = {
    "provider": "groq",
    "model": {
        "gemini": "gemini-2.5-flash",
        "groq": "llama-3.3-70b-versatile",
        "ollama": "llama3",
        "openai": "gpt-4o-mini",
    },
    "api_key": {
        "gemini": "",
        "groq": "",
        "ollama": "",
        "openai": "",
    },
    "default_branch": "main",
    "commit_style": "conventional",
}


def load_config() -> dict[str, Any]:
    """Load config from disk, returning defaults if missing."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(cfg: dict[str, Any]) -> None:
    """Persist config to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def get_config() -> dict[str, Any]:
    """Return merged config with defaults."""
    cfg = load_config()
    # Deep merge with defaults
    merged = {
        "provider": cfg.get("provider", DEFAULTS["provider"]),
        "model": {**DEFAULTS["model"], **cfg.get("model", {})},
        "api_key": {**DEFAULTS["api_key"], **cfg.get("api_key", {})},
        "default_branch": cfg.get("default_branch", DEFAULTS["default_branch"]),
        "commit_style": cfg.get("commit_style", DEFAULTS["commit_style"]),
    }
    return merged


def is_configured() -> bool:
    """Return True if a config file exists with at least a provider set."""
    return CONFIG_FILE.exists()


def get_provider_api_key(provider: str) -> str:
    """Get API key for the given provider from config."""
    cfg = get_config()
    # Also allow environment variable overrides
    env_map = {
        "gemini": "GEMINI_API_KEY",
        "groq": "GROQ_API_KEY",
        "openai": "OPENAI_API_KEY",
        "ollama": "",
    }
    env_key = env_map.get(provider, "")
    if env_key:
        env_val = os.environ.get(env_key, "")
        if env_val:
            return env_val
    return cfg.get("api_key", {}).get(provider, "")


def get_current_provider() -> str:
    return get_config().get("provider", "gemini")


def get_model_for_provider(provider: str) -> str:
    return get_config().get("model", {}).get(provider, DEFAULTS["model"].get(provider, ""))


def mask_key(key: str) -> str:
    """Mask an API key for display."""
    if not key:
        return "<not set>"
    if len(key) <= 8:
        return "****"
    return key[:4] + "****" + key[-4:]
