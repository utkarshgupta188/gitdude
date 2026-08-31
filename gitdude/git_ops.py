"""
git_ops.py — All git operations for GitDude via GitPython.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from git import GitCommandError, InvalidGitRepositoryError, Repo


def get_repo(path: str = ".") -> Repo:
    """Return a GitPython Repo, raising a friendly error if not in a git repo."""
    try:
        return Repo(path, search_parent_directories=True)
    except InvalidGitRepositoryError:
        from gitdude.utils import error_panel
        error_panel(
            "The current directory is not inside a git repository.\n"
            "Run [bold cyan]git init[/bold cyan] or navigate to a repo first.",
            title="❌ Not a Git Repository",
        )
        import sys
        sys.exit(1)


def has_commits(repo: Repo) -> bool:
    """Return True if the repo has at least one commit (HEAD is valid)."""
    try:
        repo.head.commit  # raises ValueError on empty repo
        return True
    except (ValueError, TypeError):
        return False


def get_untracked_and_new_files(repo: Repo) -> str:
    """Return a text listing of untracked files (for repos with no commits yet)."""
    lines = []
    for f in repo.untracked_files:
        lines.append(f"new file:   {f}")
    return "\n".join(lines)


def get_untracked_diff(repo: Repo) -> str:
    """Return the content of untracked files in a pseudo-diff format."""
    diff_parts = []
    for file_path_str in repo.untracked_files:
        try:
            full_path = Path(repo.working_dir) / file_path_str
            if full_path.is_file():
                content = full_path.read_text(encoding="utf-8", errors="replace")
                # Format as a pseudo-diff for the AI
                diff_parts.append(f"--- /dev/null\n+++ b/{file_path_str}\n@@ -0,0 +1,1 @@\n+{content}")
        except Exception:
            continue
    return "\n".join(diff_parts)


def get_status(repo: Repo) -> str:
    """Return git status output."""
    return repo.git.status()


def get_staged_diff(repo: Repo) -> str:
    """Return diff of staged changes."""
    try:
        return repo.git.diff("--staged")
    except GitCommandError:
        return ""


def get_all_diff(repo: Repo) -> str:
    """Return diff of all tracked changes (staged + unstaged). Empty on a repo with no commits."""
    if not has_commits(repo):
        return ""
    try:
        return repo.git.diff("HEAD")
    except GitCommandError:
        return ""


def get_diff_unstaged(repo: Repo) -> str:
    """Return only unstaged changes."""
    try:
        return repo.git.diff()
    except GitCommandError:
        return ""


def get_branch_vs_main_diff(repo: Repo, base_branch: str = "main") -> str:
    """Return diff of current branch versus base_branch. Empty string on failure."""
    if not has_commits(repo):
        return ""
    for base in (base_branch, "master"):
        try:
            return repo.git.diff(f"{base}...HEAD")
        except GitCommandError:
            continue
    return ""


def get_log_main_diff(repo: Repo, base_branch: str = "main") -> str:
    """Return commit log of current branch vs base_branch. Empty string on failure."""
    if not has_commits(repo):
        return ""
    for base in (base_branch, "master"):
        try:
            return repo.git.log(f"{base}..HEAD", "--oneline")
        except GitCommandError:
            continue
    return ""


def get_recent_commits(repo: Repo, n: int = 30) -> list[dict]:
    """Return the last n commits as dicts with index/hash/date/author/message."""
    if not has_commits(repo):
        return []
    commits = []
    try:
        for i, commit in enumerate(repo.iter_commits(max_count=n), 1):
            commits.append({
                "index": i,
                "hash": commit.hexsha[:7],
                "date": commit.committed_datetime.strftime("%Y-%m-%d %H:%M"),
                "author": commit.author.name,
                "message": commit.message.strip().splitlines()[0],
                "full_hash": commit.hexsha,
            })
    except GitCommandError:
        pass
    return commits


def get_reflog(repo: Repo, n: int = 10) -> str:
    """Return n entries of git reflog as text."""
    try:
        return repo.git.reflog("--oneline", f"-{n}")
    except GitCommandError:
        return "(no reflog entries yet)"


def get_log_oneline(repo: Repo, n: int = 10) -> str:
    """Return last n commits as oneline log."""
    if not has_commits(repo):
        return "(no commits yet)"
    try:
        return repo.git.log("--oneline", f"-{n}")
    except GitCommandError:
        return "(no commits yet)"


def add_all(repo: Repo) -> None:
    """Stage all changes."""
    repo.git.add("--all")


def commit(repo: Repo, message: str) -> None:
    """Commit staged changes with the given message."""
    repo.git.commit("-m", message)


def push(repo: Repo, branch: str = "", remote: str = "", set_upstream: bool = False) -> str:
    """
    Push ``branch`` to ``remote`` and return stdout.

    Falls back to the current active branch and ``origin`` remote when not
    given. Raises GitCommandError so callers can inspect the real error
    (a bare retry that masks non-fast-forward rejections is avoided here).
    """
    branch = branch or repo.active_branch.name
    remote = remote or "origin"
    if set_upstream:
        return repo.git.push("--set-upstream", remote, branch)
    return repo.git.push(remote, branch)


def fetch(repo: Repo) -> str:
    return repo.git.fetch()


def pull_rebase(repo: Repo) -> str:
    return repo.git.pull("--rebase")


def get_conflict_content(repo: Repo) -> str:
    """Read content of conflicted files."""
    conflicts = []
    for path in repo.index.unmerged_blobs():
        full = Path(repo.working_dir) / path
        try:
            content = full.read_text(encoding="utf-8", errors="replace")
            conflicts.append(f"=== {path} ===\n{content}")
        except OSError:
            conflicts.append(f"=== {path} === (could not read)")
    return "\n\n".join(conflicts) if conflicts else ""


def soft_reset(repo: Repo, ref: str) -> str:
    return repo.git.reset("--soft", ref)


def hard_reset(repo: Repo, ref: str) -> str:
    return repo.git.reset("--hard", ref)


def checkout_commit(repo: Repo, ref: str) -> str:
    return repo.git.checkout(ref)


def create_branch_from(repo: Repo, ref: str, branch_name: str) -> str:
    return repo.git.checkout("-b", branch_name, ref)


def run_git_command(repo: Repo, command: str, safe: bool = False) -> tuple[bool, str]:
    """
    Execute a git command via subprocess (not GitPython).

    The command string is split into argv and run WITHOUT a shell to prevent
    command injection when the string originates from AI output. When ``safe``
    is False (default) only a ``git`` executable prefix is auto-added; every
    token is passed as a literal argument so separators like ``;``, ``&&``,
    pipes, or backticks are never interpreted by a shell.

    Returns (success: bool, output: str).
    """
    import shlex as _shlex
    argv = _shlex.split(command) if command else []
    if not argv:
        return False, "empty command"
    if argv[0] != "git":
        argv = ["git", *argv]
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            cwd=repo.working_dir,
        )
        combined = (result.stdout + result.stderr).strip()
        return result.returncode == 0, combined
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def get_current_branch(repo: Repo) -> str:
    """Return the name of the current branch."""
    try:
        return repo.active_branch.name
    except TypeError:
        return "HEAD (detached)"


def get_log(repo: Repo, count: int = 10) -> str:
    """Return the last N commit log entries as a compact string."""
    if not has_commits(repo):
        return "(no commits yet)"
    try:
        return repo.git.log("--oneline", f"-{count}", "--no-color")
    except GitCommandError:
        return "(unable to read log)"


def get_file_tree(repo: Repo, max_depth: int = 3) -> str:
    """Return a directory tree listing of the repo, ignoring common junk."""
    ignore = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".egg-info"}
    lines = []

    def _walk(directory: Path, prefix: str, depth: int):
        if depth > max_depth:
            return
        try:
            entries = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return
        for entry in entries:
            if entry.name in ignore:
                continue
            if entry.is_dir():
                lines.append(f"{prefix}📁 {entry.name}/")
                _walk(entry, prefix + "  ", depth + 1)
            else:
                lines.append(f"{prefix}📄 {entry.name}")

    root = Path(repo.working_dir)
    lines.append(f"📁 {root.name}/")
    _walk(root, "  ", 1)
    return "\n".join(lines[:200])  # Cap output


def read_file_contents(repo: Repo, paths: list[str], max_chars: int = 5000) -> str:
    """Read the content of specific files from the repo root, if they exist."""
    parts = []
    root = Path(repo.working_dir)
    total = 0
    for p in paths:
        full = root / p
        if full.is_file() and total < max_chars:
            try:
                content = full.read_text(encoding="utf-8", errors="replace")
                chunk = content[:max_chars - total]
                parts.append(f"### {p}\n```\n{chunk}\n```")
                total += len(chunk)
            except Exception:
                continue
    return "\n\n".join(parts) if parts else "(no key files found)"


def get_latest_tag(repo: Repo) -> str:
    """Return the latest tag name, or empty string if no tags exist."""
    try:
        return repo.git.describe("--tags", "--abbrev=0")
    except GitCommandError:
        return ""


def get_commits_since(repo: Repo, ref: str) -> str:
    """Return commits since the given ref as oneline log."""
    try:
        return repo.git.log(f"{ref}..HEAD", "--oneline")
    except GitCommandError:
        return ""


def create_tag(repo: Repo, tag_name: str, message: str) -> str:
    """Create an annotated tag."""
    return repo.git.tag("-a", tag_name, "-m", message)


def push_tag(repo: Repo, tag_name: str, remote: str = "") -> str:
    """Push a specific tag to a remote (defaults to origin)."""
    remote = remote or "origin"
    return repo.git.push(remote, tag_name)

