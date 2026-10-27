"""Persist research in a dedicated git branch, never overwrite source or samples."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRANCH = "moex-data"
DIRECTORIES = ("cloud_data", "cloud_state", "cloud_reports")


def git(*args, cwd=None, check=True):
    return subprocess.run(["git", *args], cwd=cwd or ROOT, check=check, capture_output=True, text=True)


def fetch_state():
    result = git("ls-remote", "--exit-code", "--heads", "origin", f"refs/heads/{BRANCH}", check=False)
    if result.returncode == 2:
        return False  # No remote branch on the first run.
    if result.returncode != 0:
        raise RuntimeError("Cannot inspect remote state; refusing to initialize over an unreadable ledger")
    git("fetch", "origin", f"refs/heads/{BRANCH}:refs/remotes/origin/{BRANCH}")
    return True


def restore():
    if not fetch_state():
        print("First cloud run: no persistent ledger yet")
        return
    tracked = git("ls-tree", "-r", "--name-only", f"origin/{BRANCH}").stdout.splitlines()
    for name in tracked:
        parts = Path(name).parts
        if not parts or parts[0] not in DIRECTORIES or ".." in parts:
            continue
        destination = ROOT / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        data = subprocess.run(["git", "show", f"origin/{BRANCH}:{name}"], cwd=ROOT, check=True, capture_output=True).stdout
        destination.write_bytes(data)
    print("Restored market data and forward ledger from moex-data")


def publish():
    # The state must have been restored before calculation. Refuse a reset if
    # a remote journal exists and this working copy lacks its original prefix.
    existed = fetch_state()
    if existed:
        for name in ("forecasts.jsonl", "outcomes.jsonl"):
            key = f"cloud_state/{name}"
            previous = subprocess.run(["git", "show", f"origin/{BRANCH}:{key}"], cwd=ROOT, capture_output=True)
            if previous.returncode == 0:
                current = ROOT / key
                if not current.exists() or not current.read_bytes().startswith(previous.stdout):
                    raise RuntimeError(f"Refusing non-append change to {key}")
    parent = Path(tempfile.mkdtemp(prefix="moex-publish-"))
    work = parent / "state"
    try:
        git("worktree", "add", "--detach", str(work), f"origin/{BRANCH}" if existed else "HEAD")
        if not existed:
            git("checkout", "--orphan", BRANCH, cwd=work)
            git("rm", "-rf", ".", cwd=work)
        for directory in DIRECTORIES:
            source = ROOT / directory
            if source.exists():
                shutil.copytree(source, work / directory, dirs_exist_ok=True)
        (work / "README.md").write_text(
            "# MOEX cloud results\n\nOpen [latest report](cloud_reports/latest.md). "
            "Source code and the scheduled workflow are on the default branch. "
            "Only research data and append-only forecast/outcome ledgers live here.\n",
            encoding="utf-8")
        git("add", "--all", cwd=work)
        if git("diff", "--cached", "--quiet", cwd=work, check=False).returncode == 0:
            print("No state changes")
            return
        git("-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit", "-m", "Update MOEX research and append forecast outcomes", cwd=work)
        git("push", "origin", f"HEAD:refs/heads/{BRANCH}", cwd=work)
        print("Saved research state to moex-data")
    finally:
        git("worktree", "remove", "--force", str(work), check=False)
        shutil.rmtree(parent, ignore_errors=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("restore", "publish"))
    command = parser.parse_args().action
    (restore if command == "restore" else publish)()
