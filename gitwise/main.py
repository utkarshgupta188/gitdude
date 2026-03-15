"""
main.py — GitDude CLI: Typer app with all command definitions.
"""

from __future__ import annotations

import sys
from typing import Optional

import typer
from rich.console import Console
from rich.prompt import Prompt

app = typer.Typer(
    name="gitdude",
    help="🧠 GitDude — AI-powered Git workflow assistant",
    add_completion=True,
    rich_markup_mode="rich",
    no_args_is_help=True,
)

console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_configured() -> None:
    """Trigger interactive config setup if not yet configured."""
    from gitwise.config import is_configured
    if not is_configured():
        console.print(
            "[bold yellow]⚠️  GitDude is not configured yet.[/bold yellow]\n"
            "Let's set it up now...\n"
        )
        _run_interactive_config()


def _run_interactive_config() -> None:
    """Interactive setup wizard (shared by `config` command and auto-trigger)."""
    from gitwise.config import (
        PROVIDERS, get_config, save_config, DEFAULTS, get_model_for_provider
    )
    from gitwise.utils import success_panel, info_panel, divider

    divider()
    console.print("[bold cyan]🔧 GitDude Configuration Setup[/bold cyan]")
    divider()

    existing = get_config()

    # Provider
    console.print(f"\nAvailable providers: {', '.join(PROVIDERS)}")
    provider = Prompt.ask(
        "[bold cyan]Choose AI provider[/bold cyan]",
        choices=PROVIDERS,
        default=existing.get("provider", "gemini"),
    )

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
        api_key = Prompt.ask(
            f"[bold cyan]API Key for {provider}[/bold cyan]",
            default=existing_key,
            password=True,
        )
    else:
        console.print("[dim]Ollama is local — no API key needed.[/dim]")

    # Model
    default_model = get_model_for_provider(provider)
    model = Prompt.ask(
        f"[bold cyan]Model name[/bold cyan] (default: {default_model})",
        default=default_model,
    )

    # Default branch
    default_branch = Prompt.ask(
        "[bold cyan]Default branch[/bold cyan]",
        choices=["main", "master"],
        default=existing.get("default_branch", "main"),
    )

    # Commit style
    commit_style = Prompt.ask(
        "[bold cyan]Commit message style[/bold cyan]",
        choices=["conventional", "freeform"],
        default=existing.get("commit_style", "conventional"),
    )

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
        title="✅ Configuration Saved",
    )


# ---------------------------------------------------------------------------
# gitdude push
# ---------------------------------------------------------------------------

@app.command("push")
def cmd_push(
    no_confirm: bool = typer.Option(False, "--no-confirm", help="Skip confirmation prompt"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen, don't execute"),
    style: str = typer.Option("", "--style", help="Commit style: conventional or freeform"),
):
    """
    [bold green]AI-generated commit message + push.[/bold green]

    Stages all changes, generates a commit message via AI, and pushes.
    """
    _ensure_configured()
    from gitwise import git_ops
    from gitwise.ai import ask_ai
    from gitwise.config import get_config
    from gitwise.utils import (
        ai_panel, error_panel, success_panel, warning_panel,
        confirm, ask, info_panel, console as _c
    )
    from rich.prompt import Prompt as _Prompt

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
        staged = git_ops.get_staged_diff(repo)
        if not staged:
            all_diff = git_ops.get_all_diff(repo)
            if not all_diff:
                all_diff = git_ops.get_diff_unstaged(repo)
            diff_text = all_diff
            _c.print("[dim]No staged changes detected — using full working tree diff.[/dim]")
        else:
            diff_text = staged

    if not diff_text.strip():
        warning_panel("No changes detected (nothing staged or modified). Nothing to commit.", title="⚠️  Nothing to Commit")
        raise typer.Exit(0)

    # Build prompt
    style_instructions = (
        "Use the Conventional Commits format: type(scope): description\n"
        "Types: feat, fix, chore, docs, refactor, style, test, perf, ci\n"
        "Keep the subject line under 72 characters."
        if commit_style == "conventional"
        else "Write a clear, concise commit message in plain English."
    )
    prompt = (
        f"You are an expert software engineer writing a git commit message.\n\n"
        f"Commit style instruction:\n{style_instructions}\n\n"
        f"Git status:\n{status}\n\n"
        f"Git diff:\n{diff_text[:8000]}\n\n"
        "Respond with ONLY the commit message. No explanation, no markdown, no quotes."
    )

    commit_msg = ask_ai(prompt, spinner_msg="🤖 Generating commit message...")
    commit_msg = commit_msg.strip().strip('"').strip("'")

    ai_panel(f"[bold]{commit_msg}[/bold]", title="🤖 Suggested Commit Message")

    if dry_run:
        info_panel("Dry run mode — no changes made.", title="🧪 Dry Run")
        raise typer.Exit(0)

    # Confirm / Edit / Cancel
    action = _Prompt.ask(
        "[bold cyan]Action[/bold cyan]",
        choices=["confirm", "edit", "cancel"],
        default="confirm",
    ) if not no_confirm else "confirm"

    if action == "cancel":
        _c.print("[dim]Cancelled.[/dim]")
        raise typer.Exit(0)

    if action == "edit":
        commit_msg = ask("Edit commit message", default=commit_msg)

    try:
        if not is_first_commit:
            git_ops.add_all(repo)
            _c.print("[dim]📦 Staging all changes...[/dim]")
        else:
            _c.print("[dim]📦 All files already staged.[/dim]")
        git_ops.commit(repo, commit_msg)
        _c.print("[dim]💾 Committed.[/dim]")
        push_output = git_ops.push(repo)
        success_panel(
            f"Commit: [bold]{commit_msg}[/bold]\n{push_output}",
            title="✅ Pushed Successfully",
        )
    except Exception as exc:  # noqa: BLE001
        error_panel(f"Push failed:\n{exc}", title="❌ Push Failed")
        raise typer.Exit(1)


# ---------------------------------------------------------------------------
# gitdude sync
# ---------------------------------------------------------------------------

@app.command("sync")
def cmd_sync(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen, don't execute"),
):
    """
    [bold green]Fetch + rebase. Explains merge conflicts with AI.[/bold green]
    """
    _ensure_configured()
    from gitwise import git_ops
    from gitwise.ai import ask_ai
    from gitwise.utils import success_panel, error_panel, ai_panel, warning_panel
    from git import GitCommandError

    repo = git_ops.get_repo()

    if dry_run:
        from gitwise.utils import info_panel
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
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen, don't execute"),
):
    """
    [bold green]Interactively travel back in commit history.[/bold green]
    """
    _ensure_configured()
    from gitwise import git_ops
    from gitwise.ai import ask_ai
    from gitwise.utils import (
        print_commit_table, ai_panel, confirm, ask,
        error_panel, success_panel, pick_number
    )
    from rich.prompt import Prompt as _P
    from git import GitCommandError

    repo = git_ops.get_repo()
    commits = git_ops.get_recent_commits(repo, n=30)

    if not commits:
        from gitwise.utils import warning_panel
        warning_panel("No commits found in this repository.", title="⚠️  Empty History")
        raise typer.Exit(0)

    print_commit_table(commits)

    idx = pick_number("Enter commit number to go back to", 1, len(commits))
    chosen = commits[idx - 1]
    ref = chosen["full_hash"]

    console.print(f"\n[bold]Selected:[/bold] {chosen['hash']} — {chosen['message']}")

    # Choose mode
    mode = _P.ask(
        "[bold cyan]Mode[/bold cyan]",
        choices=["soft", "hard", "checkout", "branch"],
        default="soft",
    )

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
        from gitwise.utils import info_panel
        info_panel(f"Would execute: git {'reset --' + mode if mode in ('soft','hard') else 'checkout'} {chosen['hash']}", title="🧪 Dry Run")
        raise typer.Exit(0)

    if mode == "hard":
        from gitwise.utils import danger_panel
        danger_panel(
            f"Hard reset to [bold]{chosen['hash']}[/bold] will [bold red]permanently discard[/bold red] all changes after this commit.",
            title="🚨 Destructive Operation",
        )

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


# ---------------------------------------------------------------------------
# gitdude undo
# ---------------------------------------------------------------------------

@app.command("undo")
def cmd_undo(
    description: str = typer.Argument(..., help='Describe what went wrong, e.g. "I committed my .env file"'),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen, don't execute"),
):
    """
    [bold green]AI diagnoses your git mistake and gives recovery steps.[/bold green]

    Example: gitdude undo "I accidentally committed my .env file"
    """
    _ensure_configured()
    from gitwise import git_ops
    from gitwise.ai import ask_ai
    from gitwise.utils import ai_panel, warning_panel, error_panel, success_panel, confirm, danger_panel
    from git import GitCommandError

    repo = git_ops.get_repo()
    git_log = git_ops.get_log_oneline(repo, n=15)
    status = git_ops.get_status(repo)
    reflog = git_ops.get_reflog(repo, n=10)

    prompt = (
        f"A developer needs help recovering from a git mistake.\n\n"
        f"Problem description: {description}\n\n"
        f"Git log (recent):\n{git_log}\n\n"
        f"Git status:\n{status}\n\n"
        f"Git reflog:\n{reflog}\n\n"
        "Please:\n"
        "1. Identify exactly what happened\n"
        "2. Suggest the safest recovery command(s) — one per line, starting with 'COMMAND:'\n"
        "3. Warn clearly if any step is destructive (data loss)\n"
        "4. Explain each command briefly\n"
        "Format: plain text, no markdown code blocks."
    )

    analysis = ask_ai(prompt, spinner_msg="🤖 Diagnosing the issue...")

    # Parse out commands
    lines = analysis.splitlines()
    commands = [l.replace("COMMAND:", "").strip() for l in lines if l.strip().startswith("COMMAND:")]
    explanation_lines = [l for l in lines if not l.strip().startswith("COMMAND:")]
    explanation = "\n".join(explanation_lines).strip()

    ai_panel(explanation, title="🤖 Diagnosis & Recovery Plan")

    if commands:
        from gitwise.utils import print_command_table
        print_command_table(commands, title="Recovery Commands")

        destructive_keywords = {"--hard", "--force", "-f", "reset", "rm", "clean"}
        is_destructive = any(kw in " ".join(commands) for kw in destructive_keywords)
        if is_destructive:
            danger_panel(
                "One or more recovery commands are [bold red]destructive[/bold red] and cannot be undone.\nReview carefully before confirming.",
                title="🚨 Destructive Warning",
            )

        if dry_run:
            from gitwise.utils import info_panel
            info_panel("Dry run — no commands executed.", title="🧪 Dry Run")
            raise typer.Exit(0)

        if confirm("Execute these recovery commands?", default=False):
            for cmd in commands:
                ok, out = git_ops.run_git_command(repo, cmd)
                if ok:
                    console.print(f"[green]✓ {cmd}[/green]\n{out}")
                else:
                    error_panel(f"Command failed: {cmd}\n{out}", title="❌ Command Failed")
                    raise typer.Exit(1)
            success_panel("Recovery complete!", title="✅ Done")
        else:
            console.print("[dim]Cancelled.[/dim]")


# ---------------------------------------------------------------------------
# gitdude do
# ---------------------------------------------------------------------------

@app.command("do")
def cmd_do(
    request: str = typer.Argument(..., help='Natural language git request, e.g. "stash my changes and switch to main"'),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen, don't execute"),
):
    """
    [bold green]Execute git operations from natural language.[/bold green]

    Example: gitdude do "stash my changes, switch to main, pull latest"
    """
    _ensure_configured()
    from gitwise import git_ops
    from gitwise.ai import ask_ai
    from gitwise.utils import (
        ai_panel, print_command_table, error_panel, success_panel,
        confirm, info_panel, warning_panel
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
        from gitwise.utils import warning_panel
        warning_panel(
            f"AI could not determine git commands for:\n[italic]{request}[/italic]\n\nRaw response:\n{raw}",
            title="⚠️  No Commands Generated",
        )
        raise typer.Exit(1)

    print_command_table(commands, title="Git Commands to Execute")

    if warnings:
        from gitwise.utils import warning_panel as wp
        wp("\n".join(f"• {w}" for w in warnings), title="⚠️  AI Warnings")

    if dry_run:
        info_panel("Dry run — no commands executed.", title="🧪 Dry Run")
        raise typer.Exit(0)

    if not confirm(f"Execute {len(commands)} command(s)?"):
        console.print("[dim]Cancelled.[/dim]")
        raise typer.Exit(0)

    for cmd in commands:
        console.print(f"\n[bold yellow]▶ {cmd}[/bold yellow]")
        ok, out = git_ops.run_git_command(repo, cmd)
        if out:
            console.print(f"[dim]{out}[/dim]")
        if not ok:
            prompt2 = (
                f"This git command failed:\n{cmd}\n\n"
                f"Error output:\n{out}\n\n"
                "Explain why it failed and suggest a fix in 2-3 sentences."
            )
            fix = ask_ai(prompt2, spinner_msg="🤖 Diagnosing failure...")
            ai_panel(fix, title="🤖 Error Analysis & Suggested Fix")
            raise typer.Exit(1)

    success_panel(f"All {len(commands)} command(s) executed successfully.", title="✅ Done")


# ---------------------------------------------------------------------------
# gitdude review
# ---------------------------------------------------------------------------

@app.command("review")
def cmd_review(
    base: str = typer.Option("", "--base", help="Base branch to compare against (default: main/master)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show diff only, don't call AI"),
):
    """
    [bold green]AI pre-push code review: bugs, security, quality.[/bold green]
    """
    _ensure_configured()
    from gitwise import git_ops
    from gitwise.ai import ask_ai
    from gitwise.config import get_config
    from gitwise.utils import ai_panel, info_panel, warning_panel, error_panel

    repo = git_ops.get_repo()
    cfg = get_config()
    base_branch = base or cfg.get("default_branch", "main")

    diff = git_ops.get_branch_vs_main_diff(repo, base_branch)
    if not diff.strip():
        warning_panel(f"No diff found between current branch and [bold]{base_branch}[/bold].", title="⚠️  Nothing to Review")
        raise typer.Exit(0)

    if dry_run:
        info_panel(f"Would review diff vs [bold]{base_branch}[/bold] ({len(diff)} chars).", title="🧪 Dry Run")
        console.print(f"[dim]{diff[:2000]}[/dim]")
        raise typer.Exit(0)

    prompt = (
        f"You are a senior software engineer performing a pre-push code review.\n"
        f"Review the following git diff and produce a structured report.\n\n"
        f"Diff (vs {base_branch}):\n{diff[:10000]}\n\n"
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
    dry_run: bool = typer.Option(False, "--dry-run", help="Show diff only"),
):
    """
    [bold green]Generate a PR title + description, copy to clipboard.[/bold green]
    """
    _ensure_configured()
    from gitwise import git_ops
    from gitwise.ai import ask_ai
    from gitwise.config import get_config
    from gitwise.utils import ai_panel, info_panel, warning_panel, success_panel

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
                title="⚠️  Clipboard Unavailable",
            )


# ---------------------------------------------------------------------------
# gitdude explain
# ---------------------------------------------------------------------------

@app.command("explain")
def cmd_explain():
    """
    [bold green]AI explains your last 5 git operations in plain English.[/bold green]
    """
    _ensure_configured()
    from gitwise import git_ops
    from gitwise.ai import ask_ai
    from gitwise.utils import ai_panel

    repo = git_ops.get_repo()
    reflog = git_ops.get_reflog(repo, n=5)
    log = git_ops.get_log_oneline(repo, n=5)

    prompt = (
        "Explain the following git reflog and log entries in plain English.\n"
        "Write as if explaining to a junior developer.\n"
        "Be concise — 1-2 sentences per operation.\n\n"
        f"Reflog (last 5 operations):\n{reflog}\n\n"
        f"Commit log (last 5):\n{log}\n\n"
        "Format each entry as:\n"
        "- [operation]: plain English explanation"
    )

    explanation = ask_ai(prompt, spinner_msg="🤖 Analyzing git history...")
    ai_panel(explanation, title="🤖 What Happened (Plain English)")


# ---------------------------------------------------------------------------
# gitdude whoops
# ---------------------------------------------------------------------------

@app.command("whoops")
def cmd_whoops(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show diagnosis only, don't execute"),
):
    """
    [bold red]Emergency recovery — AI diagnoses what went wrong.[/bold red]
    """
    _ensure_configured()
    from gitwise import git_ops
    from gitwise.ai import ask_ai
    from gitwise.utils import (
        ai_panel, danger_panel, print_command_table, confirm,
        error_panel, success_panel, info_panel
    )

    repo = git_ops.get_repo()
    status = git_ops.get_status(repo)
    log = git_ops.get_log_oneline(repo, n=10)
    reflog = git_ops.get_reflog(repo, n=10)

    from gitwise.utils import warning_panel
    warning_panel(
        "Gathering diagnostic info and consulting AI...\nThis will NOT make any changes yet.",
        title="🚨 Emergency Recovery Mode",
    )

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

    if confirm("Execute the recovery commands?", default=False):
        for cmd in commands:
            console.print(f"\n[bold yellow]▶ {cmd}[/bold yellow]")
            ok, out = git_ops.run_git_command(repo, cmd)
            if out:
                console.print(f"[dim]{out}[/dim]")
            if not ok:
                error_panel(f"Command failed: {cmd}\n{out}", title="❌ Failed")
                raise typer.Exit(1)
        success_panel("Recovery commands executed.", title="✅ Done")
    else:
        console.print("[dim]No commands executed.[/dim]")


# ---------------------------------------------------------------------------
# gitdude sync (already defined above)
# gitdude config
# ---------------------------------------------------------------------------

@app.command("config")
def cmd_config(
    show: bool = typer.Option(False, "--show", help="Print current config (API keys masked)"),
    reset: bool = typer.Option(False, "--reset", help="Wipe config and re-run setup"),
):
    """
    [bold green]Interactive configuration setup for GitDude.[/bold green]
    """
    from gitwise.config import (
        get_config, save_config, CONFIG_FILE, mask_key, PROVIDERS
    )
    from gitwise.utils import info_panel, success_panel, print_key_value, divider, warning_panel

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

    _run_interactive_config()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    app()


if __name__ == "__main__":
    main()
