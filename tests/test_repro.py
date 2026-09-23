"""Repro gate (Edition gate 3) tests: the SKIP path and the drift path.

Drift test: a staged git root whose committed bytes of one artifact no
longer match what a clean-``git-archive`` pipeline re-run regenerates;
the gate must exit 1 naming exactly that ``artifacts/**`` path.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def stage_full(tmp_path: Path) -> Path:
    """A repo-shaped staged root with everything the inner pipeline needs."""
    staged = tmp_path / "repo"
    for name in ("analysis", "artifacts", "config", "scripts"):
        shutil.copytree(
            REPO_ROOT / name,
            staged / name,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    (staged / "data").mkdir()
    for name in ("ie_data.xls", "DATA.md", "RUNLOG.md"):
        shutil.copy2(REPO_ROOT / "data" / name, staged / "data" / name)
    return staged


def run_repro(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check_repro.py"), str(root)],
        capture_output=True,
        text=True,
        check=False,  # intentional: exit codes are asserted per test
    )


def git_run(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def test_repro_skip_without_git(tmp_path: Path) -> None:
    staged = stage_full(tmp_path)
    result = run_repro(staged)
    assert result.returncode == 0
    assert "SKIP: no git tree" in result.stdout


def test_repro_drift_names_the_drifted_artifact(tmp_path: Path) -> None:
    staged = stage_full(tmp_path)
    git_run(staged, "init", "-q")
    git_run(staged, "config", "user.email", "t@example.com")
    git_run(staged, "config", "user.name", "t")
    git_run(staged, "add", "-A")
    git_run(staged, "commit", "-q", "-m", "seed")

    # Drift the committed sidecar bytes away from the deterministic
    # regeneration (the CSVs stay pristine so the inner suite still
    # passes; only the gate-3 byte-diff may see the drift).
    meta = staged / "artifacts" / "series" / "canonical_60_40_annual_v1.meta.json"
    doc = json.loads(meta.read_text("utf-8"))
    doc["data_quality_notes"] = ["drifted-by-test"]
    meta.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", "utf-8")
    git_run(staged, "add", "-A")
    git_run(staged, "commit", "-q", "-m", "drift")

    result = run_repro(staged)
    assert result.returncode == 1, result.stdout + result.stderr
    assert (
        "FAIL: repro drift: artifacts/series/canonical_60_40_annual_v1.meta.json"
        in result.stderr
    )
    # Only the drifted path is named.
    assert result.stderr.count("FAIL: repro drift:") == 1
