"""
git_ops.py — All git operations for GitDude via GitPython.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

import git
from git import Repo, InvalidGitRepositoryError, GitCommandError


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
    """Return diff of current branch versus base_branch."""
    if not has_commits(repo):
        return ""
    try:
        return repo.git.diff(f"{base_branch}...HEAD")
    except GitCommandError:
        try:
            return repo.git.diff("master...HEAD")
        except GitCommandError as exc:
            return f"[Error getting diff: {exc}]"


def get_log_main_diff(repo: Repo, base_branch: str = "main") -> str:
    """Return commit log of current branch vs base_branch."""
    if not has_commits(repo):
        return ""
    try:
        return repo.git.log(f"{base_branch}..HEAD", "--oneline")
    except GitCommandError:
        try:
            return repo.git.log("master..HEAD", "--oneline")
        except GitCommandError as exc:
            return f"[Error getting log: {exc}]"


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


def push(repo: Repo) -> str:
    """Push current branch to remote. Returns stdout."""
    branch = repo.active_branch.name
    try:
        return repo.git.push("origin", branch)
    except GitCommandError:
        # Try to push with --set-upstream on first push
        return repo.git.push("--set-upstream", "origin", branch)


def fetch(repo: Repo) -> str:
    return repo.git.fetch()


def pull_rebase(repo: Repo) -> str:
    return repo.git.pull("--rebase")


def has_merge_conflicts(repo: Repo) -> bool:
    """Check if there are merge conflict markers in the working tree."""
    return repo.is_dirty(untracked_files=False) and bool(repo.index.unmerged_blobs())


def get_conflict_content(repo: Repo) -> str:
    """Read content of conflicted files."""
    conflicts = []
    for path in repo.index.unmerged_blobs():
        try:
            content = Path(path).read_text(encoding="utf-8", errors="replace")
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


def run_git_command(repo: Repo, command: str) -> tuple[bool, str]:
    """
    Execute an arbitrary git command string via subprocess (not GitPython).
    Returns (success: bool, output: str).
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
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


def stash(repo: Repo) -> str:
    return repo.git.stash()


def stash_pop(repo: Repo) -> str:
    return repo.git.stash("pop")
