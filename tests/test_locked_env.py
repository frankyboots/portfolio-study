"""Locked-sync coverage (I/O matrix row "Locked sync", NFR3).

Running under ``uv run`` means the environment already resolved from
``uv.lock``; these tests assert the resolved env is the pinned one
(Python 3.12, pandas 3.0.x, matplotlib 3.11.x, all declared deps
present) and that the lockfile has not drifted from ``pyproject.toml``
(``uv lock --check`` exits non-zero on drift -- the same failure
``uv sync --locked`` enforces).
"""

import importlib.metadata
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _major_minor(dist: str) -> tuple[int, int]:
    parts = importlib.metadata.version(dist).split(".")
    return int(parts[0]), int(parts[1])


def test_resolved_env_matches_pinned_bands() -> None:
    assert sys.version_info[:2] == (3, 12), sys.version
    # Spec-pinned bands: pandas 3.0.x, matplotlib 3.11.x, pandas-stubs 3.0.x.
    assert _major_minor("pandas") == (3, 0)
    assert _major_minor("matplotlib") == (3, 11)
    assert _major_minor("pandas-stubs") == (3, 0)
    # Every declared pin resolves (exact versions live in uv.lock).
    for dist in ("numpy", "xlrd", "olefile", "pytest", "ruff", "mypy"):
        importlib.metadata.version(dist)


def test_lockfile_has_not_drifted() -> None:
    uv = shutil.which("uv")
    assert uv is not None, "uv must be on PATH (the env is uv-managed)"
    result = subprocess.run(
        [uv, "lock", "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,  # intentional: the exit code is asserted by this test
    )
    assert result.returncode == 0, result.stderr
