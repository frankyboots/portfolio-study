"""Import-wall checker tests.

Each fixture tree under ``tests/fixtures/`` mirrors the
``analysis/<layer>/...`` layout; the checker infers layer rank from that
subpath. The clean skeleton must pass; each violation fixture must make
the checker exit non-zero with the offending rule and file named.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "scripts" / "check_import_walls.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def run_checker(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), str(root)],
        capture_output=True,
        text=True,
        check=False,  # intentional: the exit code is asserted by each test
    )


def test_clean_skeleton_passes() -> None:
    result = run_checker(FIXTURES / "clean")
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_real_repo_tree_passes() -> None:
    """The build must be green on the real tree."""
    result = run_checker(REPO_ROOT)
    assert result.returncode == 0, result.stderr


def test_upward_import_fails() -> None:
    result = run_checker(FIXTURES / "upward_import")
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "upward-import" in output
    assert "analysis/metrics/bad.py" in output
    # per-violation message: file, line, offending target, rule
    assert ":3: upward-import" in output
    assert "analysis.studio" in output


def test_xlrd_outside_series_fails() -> None:
    result = run_checker(FIXTURES / "xlrd_outside_series")
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "xlrd-outside-series" in output
    assert "analysis/metrics/bad.py" in output


def test_upward_path_literal_fails() -> None:
    result = run_checker(FIXTURES / "upward_path")
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "upward-path-literal" in output
    assert "analysis/series/bad.py" in output
    assert "figures" in output


def test_upward_subprocess_ref_fails() -> None:
    result = run_checker(FIXTURES / "upward_subprocess")
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "upward-subprocess" in output
    assert "analysis/series/bad.py" in output
    assert "metrics" in output


def test_more_than_one_argument_exits_two() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(CHECKER),
            str(FIXTURES / "clean"),
            str(FIXTURES / "clean"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2


def test_root_without_analysis_dir_exits_two(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(CHECKER), str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
