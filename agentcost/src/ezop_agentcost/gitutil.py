"""Thin wrappers over the git CLI."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class GitError(RuntimeError):
    pass


def git(*args: str, cwd: Path) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip()


def toplevel(cwd: Path) -> Path:
    return Path(git("rev-parse", "--show-toplevel", cwd=cwd))


def head_sha(cwd: Path) -> str:
    return git("rev-parse", "HEAD", cwd=cwd)


def is_merge_commit(cwd: Path, rev: str = "HEAD") -> bool:
    parents = git("rev-list", "--parents", "-n", "1", rev, cwd=cwd).split()
    return len(parents) > 2


def resolve(cwd: Path, rev: str) -> str:
    return git("rev-parse", "--verify", f"{rev}^{{commit}}", cwd=cwd)


def merge_base(cwd: Path, main_branch: str, remote: str = "origin", fetch: bool = True) -> str:
    """Merge base of HEAD with ``<remote>/<main_branch>``, fetching (and unshallowing if needed) first."""
    ref = f"{remote}/{main_branch}"
    if fetch:
        try:
            git("fetch", "--no-tags", remote, f"+refs/heads/{main_branch}:refs/remotes/{ref}", cwd=cwd)
        except GitError:
            ref = main_branch  # no remote (local use): fall back to the local branch
    try:
        return git("merge-base", ref, "HEAD", cwd=cwd)
    except GitError:
        if (Path(git("rev-parse", "--git-dir", cwd=cwd)) / "shallow").exists() or git(
            "rev-parse", "--is-shallow-repository", cwd=cwd
        ) == "true":
            git("fetch", "--no-tags", "--unshallow", remote, cwd=cwd)
            return git("merge-base", ref, "HEAD", cwd=cwd)
        raise GitError(
            f"cannot find the merge base of HEAD and {ref}. Check out with full history "
            "(actions/checkout with fetch-depth: 0)."
        ) from None


@contextmanager
def worktree(repo: Path, sha: str) -> Iterator[Path]:
    """A detached, temporary worktree at ``sha``."""
    path = Path(tempfile.mkdtemp(prefix="agentcost-base-"))
    shutil.rmtree(path)
    git("worktree", "add", "--detach", str(path), sha, cwd=repo)
    try:
        yield path
    finally:
        try:
            git("worktree", "remove", "--force", str(path), cwd=repo)
        except GitError:
            shutil.rmtree(path, ignore_errors=True)
