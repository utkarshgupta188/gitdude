# GitDude 🧠

[![PyPI version](https://img.shields.io/pypi/v/gitdude.svg)](https://pypi.org/project/gitdude/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Downloads](https://img.shields.io/pypi/dm/gitdude)](https://pypi.org/project/gitdude/)

**GitDude is an AI-powered Git workflow assistant that turns plain English into git actions — commit, review, recover, and understand your repo from the terminal.**

---

## ✨ Features

- 🤖 **Multi-provider AI** — Gemini (default, free), Groq (fastest), Ollama (100% local), OpenAI
- 💬 **Natural language commands** — `gitdude do "stash, switch to main, pull"`
- 🔍 **AI code review** — bugs, security issues, quality flags before you push
- 🌿 **Smart branch naming** — `gitdude branch "fix login problem"`
- 💾 **Commit only** — `gitdude commit` generates messages without pushing
- 💬 **Codebase chat** — `gitdude chat "how does X work?"`
- 🚑 **Emergency recovery** — `gitdude whoops` diagnoses and fixes git disasters
- 📋 **PR generation** — full GitHub PR description, auto-copied to clipboard
- 🏷️ **Automated Tagging** — `gitdude tag` suggests versions and generates release notes
- 🎨 **Beautiful Rich UI** — tables, panels, spinners, color-coded output
- 🔐 **Secure config** — keys stored in `~/.gitdude/config.json`, never in `.env`

---

## 🚀 Quick Start

```bash
# 1. Install
pip install gitdude

# 2. Configure (takes 60 seconds)
gitdude config

# 3. Generate an AI commit message and push
gitdude push

# 4. Ask about your code
gitdude chat "what does this project do?"

# 5. Review your code before merging
gitdude review

# 6. Something went wrong? Ask for help
gitdude whoops
```

---

## 📦 Installation

```bash
pip install gitdude
```

**Python 3.10+ required.**

---

## 🔑 Provider Setup

### Google Gemini (Default — Free)

1. Get an API key from [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Run `gitdude config` → choose `gemini` → paste key

### Groq (Fastest Free Tier)

1. Get a key at [console.groq.com/keys](https://console.groq.com/keys)
2. Run `gitdude config` → choose `groq` → paste key

### Ollama (100% Local/Offline)

1. Install Ollama: [ollama.ai](https://ollama.ai)
2. Pull a model: `ollama pull llama3`
3. Run `gitdude config` → choose `ollama` (no key needed)

### OpenAI

1. Get a key at [platform.openai.com](https://platform.openai.com/api-keys)
2. Run `gitdude config` → choose `openai` → paste key

---

## 📖 Command Reference

### `gitdude push`

AI-generates a commit message for your changes, lets you confirm/edit, then commits and pushes.

```bash
gitdude push                            # Stage all → AI commit → push
gitdude push --no-confirm               # Skip confirmation
gitdude push --dry-run                  # Preview only, don't execute
gitdude push --style freeform           # Use freeform (not conventional) commit style
gitdude push --branch feature/auth      # Push to a specific branch
gitdude push --remote upstream          # Push to a specific remote (not just origin)
gitdude push -b new-branch -r origin    # Short flags
```

**Commit types (conventional):** `feat`, `fix`, `chore`, `docs`, `refactor`, `style`, `test`, `perf`, `ci`

> **Push errors:** if the push fails, GitDude asks the AI to diagnose the error and suggest fixes. If the fix is judged **safe**, it offers to run it automatically — otherwise you're prompted to **Allow / Deny / Allow all remaining** for every command before it runs.

---

### `gitdude commit`

AI-generates a commit message for your changes, lets you confirm/edit, and commits (but does NOT push).

```bash
gitdude commit                    # Stage all → AI commit
gitdude commit --no-confirm       # Skip confirmation
gitdude commit --dry-run          # Preview only, don't execute
gitdude commit --style freeform   # Use freeform commit style
gitdude commit --branch feature   # Branch name hint (informational)
```

---

### `gitdude sync`

Fetch + rebase. If there are merge conflicts, AI explains what's conflicting and gives exact resolution steps.

```bash
gitdude sync
gitdude sync --dry-run
```

---

### `gitdude back`

Shows last 30 commits in a table. Pick one to go back to, choose a mode.

```bash
gitdude back
gitdude back --dry-run
```

**Modes:** `soft` (keep changes staged), `hard` (discard changes), `checkout` (detached HEAD), `branch` (new branch from that commit)

---

### `gitdude do "<natural language>"`

Convert plain English into a sequence of git commands, preview, then execute.

```bash
gitdude do "stash my changes, switch to main, pull latest"
gitdude do "create a new branch called feature/auth and push it"
gitdude do "squash my last 3 commits" --dry-run
```

If any command fails, AI reads the error and suggests a fix.

> **Safety:** every generated command is reviewed one-by-one with an **Allow / Deny / Allow all remaining** prompt before it runs — nothing executes without your explicit OK.

---

### `gitdude review`

Diffs your current branch vs main/master, then AI reviews for bugs, security issues, and quality.

```bash
gitdude review
gitdude review --base develop     # Compare against a different branch
gitdude review --dry-run          # Show diff without AI review
```

**Review sections:** Summary · ⚠️ Potential Bugs · 🔒 Security Issues · 📏 Code Quality · 🔍 Things to Check · ✅ Overall Assessment

---

### `gitdude branch "<description>"`

AI-generates a clean, conventional branch name from your description.

```bash
gitdude branch "fix the login timeout bug"
# → Suggests: fix/login-timeout-bug
# → Prompts: create branch / edit name / cancel
```

---

### `gitdude chat "<question>"`

Ask questions about your codebase. It reads your file tree, README, and recent history to provide specific answers.

```bash
gitdude chat "how do I add a new command to this app?"
gitdude chat "where is the AI provider logic located?"
```

---

### `gitdude pr`

Generates a complete PR title + description + bullet list + testing notes. Auto-copies to clipboard. Falls back to reviewing your local uncommitted changes if there's no branch-vs-base diff.

```bash
gitdude pr
gitdude pr --base develop         # Compare against develop
gitdude pr --no-copy              # Don't copy to clipboard
```

---

### `gitdude tag`

Scans commits since last tag, suggests next version, and generates release notes. The suggested version is validated against semantic versioning (`X.Y.Z`) before tagging.

```bash
gitdude tag
gitdude tag --no-confirm          # Skip confirmation
gitdude tag --dry-run             # Preview only
gitdude tag --remote upstream     # Push the tag to a specific remote (not just origin)
```

---

### `gitdude whoops`

Emergency recovery. Feeds git status + log + reflog to AI. Diagnoses what went wrong and gives step-by-step recovery.

```bash
gitdude whoops
gitdude whoops --dry-run          # Diagnose only, don't execute
```

> **Safety:** dangerous recovery commands are reviewed one-by-one with **Allow / Deny / Allow all remaining** before executing — you're in control of every step.

---

### `gitdude config`

Interactive configuration wizard.

```bash
gitdude config                    # Run setup
gitdude config --show             # Print current config (keys masked)
gitdude config --reset            # Wipe config and redo setup
```

**Stored settings:**
- AI provider (`gemini` / `groq` / `ollama` / `openai`)
- API key per provider
- Model name per provider
- Default branch (`main` or `master`)
- Commit style (`conventional` or `freeform`)

---

## 🏗️ Architecture

```
gitdude/
├── main.py        # Typer app — all command definitions
├── ai.py          # Unified AI provider wrapper (ask_ai)
├── git_ops.py     # GitPython operations (diff, log, push, reset…)
├── config.py      # Config at ~/.gitdude/config.json
└── utils.py       # Rich panels, tables, prompts, helpers
```

**AI Providers (`ai.py`):**

| Provider | SDK | Default Model | Speed | Cost |
|---|---|---|---|---|
| `gemini` | `google-generativeai` | `gemini-2.0-flash` | Fast | Free tier |
| `groq` | `groq` | `llama-3.3-70b-versatile` | Fastest | Free tier |
| `ollama` | `ollama` | `llama3` | Local | Free (local) |
| `openai` | `openai` | `gpt-4o-mini` | Fast | Pay per use |

All providers go through a single interface: `ask_ai(prompt) -> str` with spinner feedback and unified error handling.

---

## 🛡️ Safety Features

- ✅ **All destructive operations** (hard reset, force push, etc.) require explicit confirmation
- ✅ **Per-command Allow/Deny** — AI-suggested fixes (`gitdude do`, `whoops`) and risky push-recovery commands run only after you **Allow** each one (with an **Allow all remaining** shortcut)
- ✅ **AI safety classification** — on push errors the AI first judges whether a fix is safe; safe fixes can be auto-applied (with confirmation), risky ones go through individual review
- ✅ **`--dry-run` flag** available on all mutating commands
- ✅ **Color-coded risk levels** — green (safe), yellow (caution), red (destructive)
- ✅ **Command-injection safe** — AI-generated commands run as literal arguments (no shell), so special characters can't execute arbitrary code
- ✅ **No tracebacks** — all exceptions caught and shown as friendly Rich error panels
- ✅ **API keys** stored privately in `~/.gitdude/config.json`, never in project files

---

## 🤝 Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feat/amazing-feature`
3. Make your changes
4. Run linting: `ruff check .`
5. Open a PR — or just use `gitdude pr` to generate your PR description! 😄

**Dev setup:**
```bash
git clone https://github.com/utkarshgupta188/gitdude
cd gitdude
pip install -e ".[dev]"
```

---

## 📄 License

MIT © GitDude Contributors
