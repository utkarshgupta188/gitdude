"""
main.py — GitDude CLI: Typer app with all command definitions.
"""

from __future__ import annotations

import sys
from typing import Optional

import typer
import questionary
from rich.console import Console
from rich.prompt import Prompt

app = typer.Typer(
    name="gitdude",
    help="🧠 GitDude — AI-powered Git workflow assistant",
    add_completion=True,
    rich_markup_mode="rich")

console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_configured() -> None:
    """Trigger interactive config setup if not yet configured."""
    from gitdude.config import is_configured
    if not is_configured():
        console.print(
            "[bold yellow]⚠️  GitDude is not configured yet.[/bold yellow]\n"
            "Let's set it up now...\n"
        )
        _run_interactive_config()


def _check_for_updates() -> None:
    """Check for updates from PyPI once a day."""
    from gitdude.config import load_config, save_config
    import time
    import urllib.request
    import json

    cfg = load_config()
    last_check = cfg.get("last_update_check", 0)
    current_time = time.time()

    # Check once every 24 hours (86400 seconds)
    if current_time - last_check < 86400:
        return

    # Update last check time immediately to avoid spamming
    cfg["last_update_check"] = current_time
    save_config(cfg)

    try:
        url = "https://pypi.org/pypi/gitdude/json"
        with urllib.request.urlopen(url, timeout=2.5) as response:
            data = json.loads(response.read().decode())
            latest_version = data["info"]["version"]
            
            current_version = "1.4.0"
            try:
                import importlib.metadata
                current_version = importlib.metadata.version("gitdude")
            except Exception:
                pass

            if latest_version != current_version:
                from gitdude.utils import warning_panel
                warning_panel(
                    f"A new version of GitDude is available: [bold]{latest_version}[/bold] (Current: {current_version})\n"
                    "Run [bold]pip install --upgrade gitdude[/bold] to update.",
                    title="🚀 Update Available"
                )
    except Exception:
        pass


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """
    🧠 GitDude — AI-powered Git workflow assistant
    """
    if ctx.invoked_subcommand is None:
        from gitdude.config import is_configured
        if not is_configured():
            _ensure_configured()
        console.print(ctx.get_help())
        raise typer.Exit(0)

    # Run update check in background for actual commands
    import threading
    threading.Thread(target=_check_for_updates, daemon=True).start()


def _run_interactive_config() -> None:
    """Interactive setup wizard (shared by `config` command and auto-trigger)."""
    from gitdude.config import (
        PROVIDERS, get_config, save_config, DEFAULTS, get_model_for_provider
    )
    from gitdude.utils import custom_style, success_panel, info_panel, divider

    divider()
    console.print("[bold cyan]🔧 GitDude Configuration Setup[/bold cyan]")
    divider()

    existing = get_config()

    # Provider
    provider = questionary.select(
        "Choose AI provider",
        choices=PROVIDERS,
        default=existing.get("provider", "groq"),
        style=custom_style).ask()

    if not provider:  # Handle Ctrl+C
        raise typer.Exit(0)

    # API key
    api_key = ""
    if provider != "ollama":
        env_hints = {
            "gemini": "Get from https://aistudio.google.com/app/apikey",
            "groq": "Get from https://console.groq.com/keys",
            "openai": "Get from https://platform.openai.com/api-keys",
        }
        console.print(f"[dim]{env_hints.get(provider, '')}[/dim]")
        existing_key = existing.get("api_key", {}).get(provider, "")
        if existing_key:
            api_key = Prompt.ask(
                f"[bold cyan]API Key for {provider}[/bold cyan] (Press Enter to keep existing)",
                default="",
                password=True)
            if not api_key:
                api_key = existing_key
        else:
            api_key = Prompt.ask(
                f"[bold cyan]API Key for {provider}[/bold cyan]",
                password=True)
    else:
        console.print("[dim]Ollama is local — no API key needed.[/dim]")

    # Model
    default_model = get_model_for_provider(provider)
    model = Prompt.ask(
        f"[bold cyan]Model name[/bold cyan] (default: {default_model})",
        default=default_model)

    # Default branch
    default_branch = questionary.text(
        "Default branch (e.g. main, master, or custom)",
        default=existing.get("default_branch", "main"),
        style=custom_style).ask()

    if not default_branch:
        raise typer.Exit(0)

    # Commit style
    commit_style = questionary.select(
        "Commit message style",
        choices=["conventional", "freeform"],
        default=existing.get("commit_style", "conventional"),
        style=custom_style).ask()

    if not commit_style:
        raise typer.Exit(0)

    # Build and save
    cfg = existing.copy()
    cfg["provider"] = provider
    cfg["default_branch"] = default_branch
    cfg["commit_style"] = commit_style
    cfg.setdefault("api_key", {})
    cfg.setdefault("model", {})
    if api_key:
        cfg["api_key"][provider] = api_key
    cfg["model"][provider] = model

    save_config(cfg)
    divider()
    success_panel(
        f"Provider: [bold]{provider}[/bold]\n"
        f"Model: [bold]{model}[/bold]\n"
        f"Default branch: [bold]{default_branch}[/bold]\n"
        f"Commit style: [bold]{commit_style}[/bold]",
        title="✅ Configuration Saved")


# ---------------------------------------------------------------------------
# gitdude push
# ---------------------------------------------------------------------------

def _shared_commit_flow(push: bool, no_confirm: bool, dry_run: bool, style: str) -> None:
    _ensure_configured()
    from gitdude import git_ops
    from gitdude.ai import ask_ai
    from gitdude.config import get_config
    from gitdude.utils import custom_style, ai_panel, info_panel, success_panel, warning_panel, error_panel, ask, console as _c
    import questionary

    repo = git_ops.get_repo()
    cfg = get_config()
    commit_style = style or cfg.get("commit_style", "conventional")

    # Get diff — handle repos with no commits yet (HEAD doesn't exist)
    is_first_commit = not git_ops.has_commits(repo)
    status = git_ops.get_status(repo)

    if is_first_commit:
        # On a new repo, stage everything first, then show what will be committed
        git_ops.add_all(repo)
        staged = git_ops.get_staged_diff(repo)
        # get_staged_diff may also be empty before any staging; fall back to listing untracked files
        if not staged:
            diff_text = git_ops.get_untracked_and_new_files(repo)
        else:
            diff_text = staged
        _c.print("[dim]🆕 No commits yet — this will be the initial commit.[/dim]")
    else:
            if staged := git_ops.get_staged_diff(repo):
                diff_text = staged
            else:
                console.print("[dim]No staged changes detected — using full working tree diff.[/dim]")
                diff_text = git_ops.get_all_diff(repo)
                if untracked := git_ops.get_untracked_diff(repo):
                    diff_text += "\n" + untracked

    if not diff_text.strip():
        warning_panel("No changes detected (nothing staged or modified). Nothing to commit.", title="⚠️  Nothing to Commit")
        raise typer.Exit(0)

    # Build prompt
    style_instructions = (
        "Use the Conventional Commits format: type(scope): description\n"
        "Types: feat, fix, chore, docs, refactor, style, test, perf, ci\n"
        "The subject line should be a concise summary of the primary change (max 50 chars).\n"
        "Keep it brief. Only use a bulleted body if there are multiple complex changes that cannot be summarized in one line."
        if commit_style == "conventional"
        else "Write a clear, concise commit message in plain English (max 50 chars for subject line). Summarize changes at a high level."
    )
    prompt = (
        f"You are an expert software engineer writing a git commit message for code changes.\n\n"
        f"IMPORTANT: Analyze the ENTIRE diff below and ensure your message covers the MOST SIGNIFICANT modifications. "
        f"Do not list every small detail or file changed. Focus on the core intent. Ignore or group minor changes (like adding a single package in package.json) if there are larger functional changes.\n\n"
        f"Style instructions:\n{style_instructions}\n\n"
        f"Git status:\n{status}\n\n"
        f"Git diff:\n{diff_text[:8000]}\n\n"
        "Respond with ONLY the commit message (subject line, and optional body). No explanation, no markdown, no quotes."
    )

    commit_msg = ask_ai(prompt, spinner_msg="🤖 Generating commit message...")
    commit_msg = commit_msg.strip().strip('"').strip("'")

    ai_panel(f"[bold]{commit_msg}[/bold]", title="🤖 Suggested Commit Message")

    if dry_run:
        info_panel("Dry run mode — no changes made.", title="🧪 Dry Run")
        raise typer.Exit(0)

    import questionary
    # Confirm / Edit / Cancel
    action = questionary.select(
        "Action",
        choices=["confirm", "edit", "cancel"],
        default="confirm",
        style=custom_style).ask() if not no_confirm else "confirm"

    if not action or action == "cancel":
        _c.print("[dim]Cancelled.[/dim]")
        raise typer.Exit(0)

    if action == "edit":
        edited_msg = questionary.text(
            "Edit commit message",
            default=commit_msg,
            style=custom_style).ask()
        if edited_msg:
            commit_msg = edited_msg.strip()

    try:
        if not is_first_commit:
            git_ops.add_all(repo)
            _c.print("[dim]📦 Staging all changes...[/dim]")
        else:
            _c.print("[dim]📦 All files already staged.[/dim]")
        git_ops.commit(repo, commit_msg)
        _c.print("[dim]💾 Committed.[/dim]")
        
        if push:
            push_output = git_ops.push(repo)
            success_panel(
                f"Commit: [bold]{commit_msg}[/bold]\n{push_output}",
                title="✅ Pushed Successfully")
        else:
            success_panel(
                f"Commit: [bold]{commit_msg}[/bold]",
                title="✅ Committed Successfully")
                
    except Exception as exc:
        if push:
            error_str = str(exc)
            
            # Check for common non-fast-forward error to give a quick response
            if "Updates were rejected because the remote contains work" in error_str or "fetch first" in error_str:
                from gitdude.utils import warning_panel, print_command_table
                warning_panel(
                    "Push rejected: Your local branch is behind the remote branch.\n"
                    "You need to integrate remote changes before you can push.",
                    title="⚠️ Push Rejected"
                )
                print_command_table(["gitdude sync", "git push"], title="Suggested Commands")
                raise typer.Exit(1)
                
            # For other errors, use AI to diagnose
            prompt = (
                f"The `git push` command failed with the following error:\n{error_str}\n\n"
                f"Please:\n"
                f"1. Explain what the error means in 1 or 2 lines in plain English.\n"
                f"2. Suggest the exact command(s) to fix it, one per line starting with 'COMMAND:'.\n"
                f"Format the response clearly without markdown code blocks."
            )
            try:
                diagnosis = ask_ai(prompt, spinner_msg="🤖 Diagnosing push failure...")
                lines = diagnosis.splitlines()
                commands = [l.replace("COMMAND:", "").strip() for l in lines if l.strip().startswith("COMMAND:")]
                explanation_lines = [l for l in lines if not l.strip().startswith("COMMAND:")]
                explanation = "\n".join(explanation_lines).strip()
                
                from gitdude.utils import print_command_table
                error_panel(explanation, title="❌ Push Failed (Diagnosis)")
                if commands:
                    print_command_table(commands, title="Suggested Commands to Fix")
            except Exception:
                # Fallback if AI fails
                error_panel(f"Push failed:\n{exc}", title="❌ Push Failed")
            raise typer.Exit(1)
        else:
            error_panel(f"Commit failed:\n{exc}", title="❌ Commit Failed")
            raise typer.Exit(1)


@app.command("push")
def cmd_push(
    no_confirm: bool = typer.Option(False, "--no-confirm", help="Skip confirmation prompt"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen, don't execute"),
    style: str = typer.Option("", "--style", help="Commit style: conventional or freeform")):
    """
    [bold green]AI-generated commit message + push.[/bold green]

    Stages all changes, generates a commit message via AI, and pushes.
    """
    _shared_commit_flow(push=True, no_confirm=no_confirm, dry_run=dry_run, style=style)


@app.command("commit")
def cmd_commit(
    no_confirm: bool = typer.Option(False, "--no-confirm", help="Skip confirmation prompt"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen, don't execute"),
    style: str = typer.Option("", "--style", help="Commit style: conventional or freeform")):
    """
    [bold green]AI-generated commit message only (no push).[/bold green]

    Stages all changes, generates a commit message via AI, and commits.
    """
    _shared_commit_flow(push=False, no_confirm=no_confirm, dry_run=dry_run, style=style)


@app.command("tag")
def cmd_tag(
    no_confirm: bool = typer.Option(False, "--no-confirm", help="Skip confirmation prompt"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen, don't execute")
):
    """
    [bold green]AI-powered release tagging.[/bold green]

    Scans commits since last tag, suggests next version, and generates release notes.
    """
    _ensure_configured()
    from gitdude import git_ops
    from gitdude.ai import ask_ai
    from gitdude.utils import custom_style, ai_panel, info_panel, success_panel, warning_panel, error_panel, ask, console as _c
    import questionary

    repo = git_ops.get_repo()
    
    # Get latest tag
    latest_tag = git_ops.get_latest_tag(repo)
    if not latest_tag:
        _c.print("[dim]No tags found in the repository. Starting from v0.1.0.[/dim]")
        base_ref = "HEAD" # Fallback if no tags
        current_version = "0.1.0"
    else:
        _c.print(f"[dim]Latest tag found: [bold]{latest_tag}[/bold][/dim]")
        base_ref = latest_tag
        current_version = latest_tag.lstrip('v')

    # Get commits since last tag
    if base_ref == "HEAD":
        # If no tags, just get last 10 commits
        commits_log = git_ops.get_log_oneline(repo, n=10)
    else:
        commits_log = git_ops.get_commits_since(repo, base_ref)

    if not commits_log.strip():
        warning_panel("No commits found since the last tag. Nothing to release!", title="⚠️ No New Commits")
        raise typer.Exit(0)

    # Build prompt for AI
    prompt = (
        f"You are an expert software engineer generating release notes and suggesting a new version.\n\n"
        f"Current version: {current_version}\n\n"
        f"Here are the commits since the last release:\n{commits_log}\n\n"
        f"Please:\n"
        f"1. Suggest the next version number (Semantic Versioning: Major, Minor, or Patch).\n"
        f"2. Write a concise, bulleted list of release notes summarizing the changes.\n\n"
        f"Format your response EXACTLY like this:\n"
        f"SUGGESTED_VERSION: X.Y.Z\n"
        f"RELEASE_NOTES:\n"
        f"* Change 1\n"
        f"* Change 2"
    )

    _c.print("[dim]Analyzing commits and generating release notes...[/dim]")
    try:
        response = ask_ai(prompt, spinner_msg="🤖 Analyzing release...")
        
        # Parse response
        lines = response.splitlines()
        suggested_version = ""
        release_notes = []
        is_notes = False
        
        for line in lines:
            if line.startswith("SUGGESTED_VERSION:"):
                suggested_version = line.replace("SUGGESTED_VERSION:", "").strip()
            elif line.startswith("RELEASE_NOTES:"):
                is_notes = True
            elif is_notes and line.strip():
                release_notes.append(line.strip())
                
        if not suggested_version:
            suggested_version = current_version # Fallback
            
        notes_text = "\n".join(release_notes).strip()
        
        # Show results
        ai_panel(
            f"Suggested Version: [bold green]v{suggested_version}[/bold green]\n\n"
            f"Release Notes:\n{notes_text}",
            title="🏷️ Suggested Release"
        )
        
        if dry_run:
            from gitdude.utils import info_panel
            info_panel("Dry run mode — no changes made.", title="🧪 Dry Run")
            raise typer.Exit(0)
            
        # Ask for confirmation or edit
        if not no_confirm:
            action = questionary.select(
                "What would you like to do?",
                choices=["Create and Push Tag", "Edit Version/Notes", "Cancel"],
                style=custom_style
            ).ask()
            
            if action == "Cancel" or not action:
                raise typer.Exit(0)
            elif action == "Edit Version/Notes":
                suggested_version = questionary.text("Enter version (without v):", default=suggested_version, style=custom_style).ask()
                notes_text = questionary.text("Enter release notes:", default=notes_text, style=custom_style).ask()
                if not suggested_version:
                    raise typer.Exit(0)
        
        tag_name = f"v{suggested_version}"
        
        # Create tag
        _c.print(f"[dim]Creating tag {tag_name}...[/dim]")
        git_ops.create_tag(repo, tag_name, notes_text)
        
        # Push tag
        _c.print(f"[dim]Pushing tag {tag_name} to origin...[/dim]")
        try:
            git_ops.push_tag(repo, tag_name)
            success_panel(f"Successfully created and pushed tag [bold]{tag_name}[/bold]!", title="✅ Release Complete")
        except Exception as exc:
            warning_panel(f"Tag created locally but failed to push:\n{exc}", title="⚠️ Push Failed")
            
    except Exception as exc:
        error_panel(f"Failed to generate release notes:\n{exc}", title="❌ Tag Command Failed")
        raise typer.Exit(1)# ---------------------------------------------------------------------------
# gitdude sync
# ---------------------------------------------------------------------------

@app.command("sync")
def cmd_sync(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen, don't execute")):
    """
    [bold green]Fetch + rebase. Explains merge conflicts with AI.[/bold green]
    """
    _ensure_configured()
    from gitdude import git_ops
    from gitdude.ai import ask_ai
    from gitdude.utils import custom_style, success_panel, error_panel, ai_panel, warning_panel
    from git import GitCommandError

    repo = git_ops.get_repo()

    if dry_run:
        from gitdude.utils import info_panel
        info_panel("Would run: git fetch && git pull --rebase", title="🧪 Dry Run")
        raise typer.Exit(0)

    console.print("[dim]🔄 Fetching from remote...[/dim]")
    try:
        git_ops.fetch(repo)
    except GitCommandError as exc:
        error_panel(f"Fetch failed:\n{exc}", title="❌ Fetch Failed")
        raise typer.Exit(1)

    console.print("[dim]🔄 Rebasing...[/dim]")
    try:
        output = git_ops.pull_rebase(repo)
        success_panel(output or "Up to date.", title="✅ Sync Complete")
    except GitCommandError as exc:
        error_str = str(exc)
        conflict_content = git_ops.get_conflict_content(repo)
        if conflict_content:
            prompt = (
                "A git rebase resulted in merge conflicts. Analyze these conflicts and explain:\n"
                "1. What is conflicting and why\n"
                "2. Step-by-step resolution instructions\n"
                "3. The git commands to continue or abort the rebase\n\n"
                f"Conflicted files:\n{conflict_content[:6000]}"
            )
            explanation = ask_ai(prompt, spinner_msg="🤖 Analyzing conflicts...")
            ai_panel(explanation, title="🤖 Conflict Explanation & Resolution")
        else:
            error_panel(f"Sync failed:\n{error_str}", title="❌ Sync Failed")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# gitdude back
# ---------------------------------------------------------------------------

@app.command("back")
def cmd_back(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen, don't execute")):
    """
    [bold green]Interactively travel back in commit history.[/bold green]
    """
    _ensure_configured()
    from gitdude import git_ops
    from gitdude.ai import ask_ai
    from gitdude.utils import (
    custom_style,
        print_commit_table, ai_panel, confirm, ask,
        error_panel, success_panel, pick_number
    )
    from rich.prompt import Prompt as _P
    from git import GitCommandError

    repo = git_ops.get_repo()
    commits = git_ops.get_recent_commits(repo, n=30)

    if not commits:
        from gitdude.utils import warning_panel
        warning_panel("No commits found in this repository.", title="⚠️  Empty History")
        raise typer.Exit(0)

    print_commit_table(commits)

    idx = pick_number("Enter commit number to go back to", 1, len(commits))
    chosen = commits[idx - 1]
    ref = chosen["full_hash"]

    console.print(f"\n[bold]Selected:[/bold] {chosen['hash']} — {chosen['message']}")

    # Choose mode
    mode = questionary.select(
        "Mode",
        choices=["soft", "hard", "checkout", "branch"],
        default="soft",
        style=custom_style).ask()

    if not mode:
        return

    # AI explanation
    mode_prompts = {
        "soft": "soft reset (--soft): moves HEAD to this commit but keeps all changes staged",
        "hard": "hard reset (--hard): moves HEAD to this commit and DISCARDS all changes since then",
        "checkout": "git checkout to this commit: enters detached HEAD state",
        "branch": "create a new branch from this commit",
    }
    prompt = (
        f"Explain in 2-3 sentences, in plain English, what will happen when the user does a "
        f"{mode_prompts[mode]} at commit {chosen['hash']} ({chosen['message']}). "
        "Mention any risks clearly."
    )
    explanation = ask_ai(prompt, spinner_msg="🤖 Explaining what will happen...")
    ai_panel(explanation, title=f"🤖 What '{mode}' will do")

    if dry_run:
        from gitdude.utils import info_panel
        info_panel(f"Would execute: git {'reset --' + mode if mode in ('soft','hard') else 'checkout'} {chosen['hash']}", title="🧪 Dry Run")
        raise typer.Exit(0)

    if mode == "hard":
        from gitdude.utils import danger_panel
        danger_panel(
            f"Hard reset to [bold]{chosen['hash']}[/bold] will [bold red]permanently discard[/bold red] all changes after this commit.",
            title="🚨 Destructive Operation")

    if not confirm("Proceed?", default=False if mode == "hard" else True):
        console.print("[dim]Cancelled.[/dim]")
        raise typer.Exit(0)

    try:
        if mode == "soft":
            git_ops.soft_reset(repo, ref)
        elif mode == "hard":
            git_ops.hard_reset(repo, ref)
        elif mode == "checkout":
            git_ops.checkout_commit(repo, ref)
        elif mode == "branch":
            branch_name = ask("New branch name", default=f"branch-from-{chosen['hash']}")
            git_ops.create_branch_from(repo, ref, branch_name)
        success_panel(f"Done! Mode: [bold]{mode}[/bold] → {chosen['hash']}", title="✅ Success")
    except GitCommandError as exc:
        error_panel(str(exc), title="❌ Git Error")
        raise typer.Exit(1)
def _execute_commands(repo, commands: list[str], confirm_msg: str = "Execute commands?", default_confirm: bool = True) -> None:
    from gitdude.utils import console, ai_panel, success_panel, confirm
    from gitdude.ai import ask_ai
    from gitdude import git_ops
    import typer
    
    if not confirm(confirm_msg, default=default_confirm):
        console.print("[dim]Cancelled.[/dim]")
        raise typer.Exit(0)
        
    for cmd in commands:
        console.print(f"\n[bold yellow]▶ {cmd}[/bold yellow]")
        ok, out = git_ops.run_git_command(repo, cmd)
        if out:
            console.print(f"[dim]{out}[/dim]")
        if not ok:
            prompt = (
                f"This git command failed:\n{cmd}\n\n"
                f"Error output:\n{out}\n\n"
                "Explain why it failed and suggest a fix in 2-3 sentences."
            )
            fix = ask_ai(prompt, spinner_msg="🤖 Diagnosing failure...")
            ai_panel(fix, title="🤖 Error Analysis & Suggested Fix")
            raise typer.Exit(1)
            
    success_panel(f"All {len(commands)} command(s) executed successfully.", title="✅ Done")


# ---------------------------------------------------------------------------
# gitdude do
# ---------------------------------------------------------------------------

@app.command("do")
def cmd_do(
    request: str = typer.Argument(..., help='Natural language git request, e.g. "stash my changes and switch to main"'),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen, don't execute")):
    """
    [bold green]Execute git operations from natural language.[/bold green]

    Example: gitdude do "stash my changes, switch to main, pull latest"
    """
    _ensure_configured()
    from gitdude import git_ops
    from gitdude.ai import ask_ai
    from gitdude.utils import (
        custom_style,
        ai_panel, print_command_table, error_panel, success_panel,
        confirm, info_panel, warning_panel, console
    )

    repo = git_ops.get_repo()
    branch = git_ops.get_current_branch(repo)
    status = git_ops.get_status(repo)

    prompt = (
        f"You are a git expert. Convert the following natural language git request into an ordered sequence of git commands.\n\n"
        f"Request: {request}\n\n"
        f"Current branch: {branch}\n"
        f"Git status:\n{status}\n\n"
        "Rules:\n"
        "- Output ONLY git commands, one per line, prefixed with 'CMD:'\n"
        "- Do not include explanations between commands\n"
        "- Use safe defaults (no force flags unless explicitly requested)\n"
        "- If the request is ambiguous or risky, add a WARNING: line before the relevant CMD\n"
        "Format:\n"
        "CMD: git stash\n"
        "CMD: git checkout main\n"
        "CMD: git pull --rebase\n"
    )

    raw = ask_ai(prompt, spinner_msg="🤖 Planning git commands...")
    lines = raw.splitlines()

    commands = [l.replace("CMD:", "").strip() for l in lines if l.strip().startswith("CMD:")]
    warnings = [l.replace("WARNING:", "").strip() for l in lines if l.strip().startswith("WARNING:")]

    if not commands:
        from gitdude.utils import warning_panel
        warning_panel(
            f"AI could not determine git commands for:\n[italic]{request}[/italic]\n\nRaw response:\n{raw}",
            title="⚠️  No Commands Generated")
        raise typer.Exit(1)

    print_command_table(commands, title="Git Commands to Execute")

    if warnings:
        from gitdude.utils import warning_panel as wp
        wp("\n".join(f"• {w}" for w in warnings), title="⚠️  AI Warnings")

    if dry_run:
        info_panel("Dry run — no commands executed.", title="🧪 Dry Run")
        raise typer.Exit(0)

    _execute_commands(repo, commands, confirm_msg=f"Execute {len(commands)} command(s)?")


# ---------------------------------------------------------------------------
# gitdude review
# ---------------------------------------------------------------------------

@app.command("review")
def cmd_review(
    base: str = typer.Option("", "--base", help="Base branch to compare against (default: main/master)"),
    local: bool = typer.Option(False, "--local", help="Review only local uncommitted changes"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show diff only, don't call AI")):
    """
    [bold green]AI pre-push code review: bugs, security, quality.[/bold green]
    """
    _ensure_configured()
    from gitdude import git_ops
    from gitdude.ai import ask_ai
    from gitdude.config import get_config
    from gitdude.utils import custom_style, ai_panel, info_panel, warning_panel, error_panel

    repo = git_ops.get_repo()
    cfg = get_config()
    base_branch = base or cfg.get("default_branch", "main")

    diff = ""
    mode_label = ""

    if local:
        diff = git_ops.get_all_diff(repo)
        if not diff:
            diff = git_ops.get_diff_unstaged(repo)
        mode_label = "local changes"
    else:
        # Try branch diff first
        diff = git_ops.get_branch_vs_main_diff(repo, base_branch)
        mode_label = f"diff vs {base_branch}"
        
        # Fallback to local if branch diff is empty (common on main branch)
        if not diff.strip():
            local_diff = git_ops.get_all_diff(repo)
            if not local_diff:
                local_diff = git_ops.get_diff_unstaged(repo)
            
            if local_diff.strip():
                diff = local_diff
                mode_label = "local uncommitted changes (no branch diff found)"

    if not diff.strip():
        warning_panel(
            f"No changes found to review ({mode_label}).\n"
            "Stage some changes or commit them to a branch first.",
            title="⚠️  Nothing to Review"
        )
        raise typer.Exit(0)

    if dry_run:
        info_panel(f"Would review {mode_label} ({len(diff)} chars).", title="🧪 Dry Run")
        console.print(f"[dim]{diff[:2000]}[/dim]")
        raise typer.Exit(0)

    prompt = (
        f"You are a senior software engineer performing a pre-push code review.\n"
        f"Review the following code changes ({mode_label}) and produce a structured report.\n\n"
        f"Diff:\n{diff[:10000]}\n\n"
        "Structure your report as:\n\n"
        "## Summary\n(one line of what changed)\n\n"
        "## ⚠️ Potential Bugs\n(list items, or 'None found')\n\n"
        "## 🔒 Security Issues\n(hardcoded secrets, injection risks, etc., or 'None found')\n\n"
        "## 📏 Code Quality\n(style, complexity, naming, or 'Looks good')\n\n"
        "## 🔍 Things to Double-Check\n(edge cases, tests needed, etc.)\n\n"
        "## ✅ Overall Assessment\n(LGTM / Minor issues / Needs work)\n\n"
        "Be specific and actionable. Reference line numbers or identifiers when possible."
    )

    review = ask_ai(prompt, spinner_msg="🤖 Reviewing your code...")
    ai_panel(review, title=f"🤖 Code Review vs {base_branch}")


# ---------------------------------------------------------------------------
# gitdude pr
# ---------------------------------------------------------------------------

@app.command("pr")
def cmd_pr(
    base: str = typer.Option("", "--base", help="Base branch to compare against"),
    no_copy: bool = typer.Option(False, "--no-copy", help="Don't copy to clipboard"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show diff only")):
    """
    [bold green]Generate a PR title + description, copy to clipboard.[/bold green]
    """
    _ensure_configured()
    from gitdude import git_ops
    from gitdude.ai import ask_ai
    from gitdude.config import get_config
    from gitdude.utils import custom_style, ai_panel, info_panel, warning_panel, success_panel

    repo = git_ops.get_repo()
    cfg = get_config()
    base_branch = base or cfg.get("default_branch", "main")

    diff = git_ops.get_branch_vs_main_diff(repo, base_branch)
    log = git_ops.get_log_main_diff(repo, base_branch)
    current_branch = git_ops.get_current_branch(repo)

    if not diff.strip() and not log.strip():
        warning_panel(f"No changes found between [bold]{current_branch}[/bold] and [bold]{base_branch}[/bold].", title="⚠️  Nothing to PR")
        raise typer.Exit(0)

    if dry_run:
        info_panel(f"Would generate PR for branch [bold]{current_branch}[/bold] vs [bold]{base_branch}[/bold].", title="🧪 Dry Run")
        raise typer.Exit(0)

    prompt = (
        f"You are a senior engineer writing a GitHub Pull Request.\n"
        f"Current branch: {current_branch}\n"
        f"Base branch: {base_branch}\n\n"
        f"Commit log:\n{log}\n\n"
        f"Diff:\n{diff[:8000]}\n\n"
        "Generate a complete PR submission with the following sections:\n\n"
        "## PR Title\n(Conventional format: type(scope): short description)\n\n"
        "## Description\n(What changed and why — 2-4 sentences)\n\n"
        "## Changes\n(Bullet list of all meaningful changes)\n\n"
        "## Testing Notes\n(How to test this, what was tested)\n\n"
        "## Checklist\n- [ ] Tests added\n- [ ] Docs updated\n- [ ] No debug code left\n\n"
        "Be professional, concise, and specific."
    )

    pr_text = ask_ai(prompt, spinner_msg="🤖 Generating PR description...")
    ai_panel(pr_text, title=f"🤖 PR: {current_branch} → {base_branch}")

    if not no_copy:
        try:
            import pyperclip  # type: ignore
            pyperclip.copy(pr_text)
            success_panel("PR description copied to clipboard! 📋", title="✅ Copied")
        except Exception:  # noqa: BLE001
            warning_panel(
                "Could not copy to clipboard. Run [bold]pip install pyperclip[/bold] or check your system clipboard support.",
                title="⚠️  Clipboard Unavailable")





# ---------------------------------------------------------------------------
# gitdude whoops
# ---------------------------------------------------------------------------

@app.command("whoops")
def cmd_whoops(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show diagnosis only, don't execute")):
    """
    [bold red]Emergency recovery — AI diagnoses what went wrong.[/bold red]
    """
    _ensure_configured()
    from gitdude import git_ops
    from gitdude.ai import ask_ai
    from gitdude.utils import (
    custom_style,
        ai_panel, danger_panel, print_command_table, confirm,
        error_panel, success_panel, info_panel
    )

    repo = git_ops.get_repo()
    status = git_ops.get_status(repo)
    log = git_ops.get_log_oneline(repo, n=10)
    reflog = git_ops.get_reflog(repo, n=10)

    from gitdude.utils import warning_panel
    warning_panel(
        "Gathering diagnostic info and consulting AI...\nThis will NOT make any changes yet.",
        title="🚨 Emergency Recovery Mode")

    prompt = (
        "A developer is in trouble with their git repository. Diagnose what went wrong and provide recovery steps.\n\n"
        f"Git status:\n{status}\n\n"
        f"Recent commits:\n{log}\n\n"
        f"Reflog:\n{reflog}\n\n"
        "Please:\n"
        "1. Diagnose what likely went wrong (be specific)\n"
        "2. Provide step-by-step recovery commands, one per line, prefixed with 'COMMAND:'\n"
        "3. Mark dangerous commands with 'DANGER:' prefix\n"
        "4. Explain each step briefly\n"
        "5. End with the safest path to a clean state"
    )

    diagnosis = ask_ai(prompt, spinner_msg="🤖 Diagnosing your repository...")

    lines = diagnosis.splitlines()
    commands = [l.replace("COMMAND:", "").strip() for l in lines if l.strip().startswith("COMMAND:")]
    dangerous = [l.replace("DANGER:", "").strip() for l in lines if l.strip().startswith("DANGER:")]
    explanation_lines = [l for l in lines if not l.strip().startswith(("COMMAND:", "DANGER:"))]

    ai_panel("\n".join(explanation_lines), title="🤖 Diagnosis")

    if commands:
        print_command_table(commands, title="Recovery Commands")

    if dangerous:
        danger_panel("\n".join(f"• {d}" for d in dangerous), title="🚨 Dangerous Steps — Review Carefully")

    if dry_run or not commands:
        info_panel("Dry run or no commands — nothing executed.", title="🧪 Dry Run")
        raise typer.Exit(0)

    _execute_commands(repo, commands, confirm_msg="Execute the recovery commands?", default_confirm=False)


# ---------------------------------------------------------------------------
# gitdude sync (already defined above)
# gitdude config
# ---------------------------------------------------------------------------

@app.command("config")
def cmd_config(
    show: bool = typer.Option(False, "--show", help="Print current config (API keys masked)"),
    reset: bool = typer.Option(False, "--reset", help="Wipe config and re-run setup")):
    """
    [bold green]Interactive configuration setup for GitDude.[/bold green]
    """
    from gitdude.config import (
        get_config, save_config, CONFIG_FILE, mask_key, PROVIDERS
    )
    from gitdude.utils import info_panel, success_panel, print_key_value, divider, warning_panel

    if reset:
        if CONFIG_FILE.exists():
            CONFIG_FILE.unlink()
            warning_panel("Configuration wiped. Re-running setup...", title="🔄 Config Reset")
        _run_interactive_config()
        return

    if show:
        cfg = get_config()
        provider = cfg.get("provider", "gemini")
        divider()
        console.print("[bold cyan]📋 GitDude Configuration[/bold cyan]")
        divider()
        print_key_value("Provider", provider)
        print_key_value("Model", cfg.get("model", {}).get(provider, "N/A"))
        for p in PROVIDERS:
            key = cfg.get("api_key", {}).get(p, "")
            if key or p == provider:
                print_key_value(f"API Key ({p})", mask_key(key))
        print_key_value("Default Branch", cfg.get("default_branch", "main"))
        print_key_value("Commit Style", cfg.get("commit_style", "conventional"))
        print_key_value("Config File", str(CONFIG_FILE))
        divider()
        return

    from gitdude.config import is_configured
    if is_configured():
        cfg = get_config()
        provider = cfg.get("provider", "gemini")
        divider()
        console.print("[bold cyan]📋 Current GitDude Configuration[/bold cyan]")
        divider()
        print_key_value("Provider", provider)
        print_key_value("Model", cfg.get("model", {}).get(provider, "N/A"))
        print_key_value("Default Branch", cfg.get("default_branch", "main"))
        print_key_value("Commit Style", cfg.get("commit_style", "conventional"))
        divider()
        
        import questionary
        from gitdude.utils import custom_style
        action = questionary.select(
            "Configuration already exists. What would you like to do?",
            choices=["Edit", "Cancel"],
            default="Edit",
            style=custom_style).ask()
            
        if not action or action == "Cancel":
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit(0)
            
    _run_interactive_config()


# ---------------------------------------------------------------------------
# branch — AI branch naming
# ---------------------------------------------------------------------------

@app.command("branch")
def cmd_branch(
    description: str = typer.Argument(..., help="Plain-English description of what the branch is for")):
    """
    [bold green]Generate a clean branch name from a description.[/bold green]
    """
    _ensure_configured()
    from gitdude import git_ops
    from gitdude.ai import ask_ai
    from gitdude.utils import custom_style, ai_panel, success_panel, warning_panel

    repo = git_ops.get_repo()

    prompt = (
        "You are an expert at naming git branches.\n"
        "Given the following description, generate a single clean branch name.\n\n"
        "Rules:\n"
        "- Use the format: type/short-descriptive-slug\n"
        "- Types: feat, fix, chore, docs, refactor, test, hotfix\n"
        "- Use lowercase, hyphens only, no spaces or special characters\n"
        "- Keep it short (max 5 words in the slug)\n"
        "- Respond with ONLY the branch name. No explanation, no quotes.\n\n"
        f"Description: {description}"
    )

    branch_name = ask_ai(prompt, spinner_msg="🧠 Generating branch name...")
    branch_name = branch_name.strip().strip('"').strip("'").replace(" ", "-").lower()

    ai_panel(f"[bold]{branch_name}[/bold]", title="🌿 Suggested Branch Name")

    action = questionary.select(
        "Action",
        choices=["create branch", "edit name", "cancel"],
        default="create branch",
        style=custom_style).ask()

    if not action or action == "cancel":
        console.print("[dim]Cancelled.[/dim]")
        raise typer.Exit(0)

    if action == "edit name":
        branch_name = questionary.text("Branch name:", default=branch_name,
        style=custom_style).ask()
        if not branch_name:
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit(0)

    try:
        repo.git.checkout("-b", branch_name)
        success_panel(f"Switched to new branch [bold]{branch_name}[/bold]", title="🌿 Branch Created")
    except Exception as e:
        warning_panel(f"Could not create branch: {e}", title="⚠️  Error")





# ---------------------------------------------------------------------------
# chat — Ask your codebase
# ---------------------------------------------------------------------------

@app.command("chat")
def cmd_chat(
    question: str = typer.Argument(..., help="Your question about the codebase")):
    """
    [bold green]Ask AI questions about your codebase.[/bold green]
    """
    _ensure_configured()
    from gitdude import git_ops
    from gitdude.ai import ask_ai
    from gitdude.utils import custom_style, ai_panel

    repo = git_ops.get_repo()
    status = git_ops.get_status(repo)
    tree = git_ops.get_file_tree(repo)
    recent_log = git_ops.get_log(repo, count=10)

    # Read key files for context
    key_files = ["README.md", "readme.md", "pyproject.toml", "package.json", "Cargo.toml", "go.mod"]
    file_context = git_ops.read_file_contents(repo, key_files)

    prompt = (
        "You are a helpful senior software engineer who knows this codebase intimately.\n"
        "Answer the user's question based on the project context provided below.\n"
        "Be specific, reference file names and functions when possible.\n\n"
        f"## Project File Tree\n{tree}\n\n"
        f"## Git Status\n{status}\n\n"
        f"## Recent Commits\n{recent_log}\n\n"
        f"## Key Files\n{file_context}\n\n"
        f"## User Question\n{question}"
    )

    answer = ask_ai(prompt, spinner_msg="🧠 Thinking about your codebase...")
    ai_panel(answer, title="💬 Answer")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------




def main() -> None:
    app()


if __name__ == "__main__":
    main()
