"""Gate 7 (export freshness) staged-root matrix.

The seed rule "committed exports fail" is retired by this story: fresh
committed exports pass; a content drift fails. One negative per diff
class (SVG, PNG, record field, VINTAGE) plus the staging failure paths.
Usage/zero-arg semantics stay in tests/test_gates_scaffold.py.
"""

from __future__ import annotations

import itertools
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE7 = REPO_ROOT / "scripts" / "check_export_freshness.py"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from analysis.figures import _records

FIGS_REL = "artifacts/figures"
NAME = "rebalance_growth_v1"
RECORD_REL = f"{FIGS_REL}/{NAME}.figure.json"


@pytest.fixture(scope="module")
def gate7_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A .git-less repo-shaped root with the committed exports on disk."""
    staged = tmp_path_factory.mktemp("gate7") / "repo"
    for name in ("analysis", "config", "artifacts"):
        shutil.copytree(
            REPO_ROOT / name,
            staged / name,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    assert (staged / RECORD_REL).is_file(), "the pilot record must exist in the repo"
    return staged


_counter = itertools.count()


@pytest.fixture
def case_root(gate7_root: Path) -> Path:
    """A throwaway copy of the module root (tamper tests mutate freely)."""
    root = gate7_root.parent / f"g7case-{next(_counter):02d}"
    shutil.copytree(gate7_root, root)
    return root


def run_gate(root: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(GATE7), str(root)],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr


def _rewrite_record(root: Path, mutate) -> None:
    path = root / RECORD_REL
    doc = json.loads(path.read_text(encoding="utf-8"))
    mutate(doc)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# --------------------------------------------------------------- positive


def test_fresh_exports_pass(case_root: Path) -> None:
    rc, out = run_gate(case_root)
    assert rc == 0, out
    assert "OK: export freshness" in out


def test_no_figures_in_tree_is_structural_pass(gate7_root: Path) -> None:
    bare = gate7_root.parent / "g7bare"
    shutil.copytree(gate7_root, bare, ignore=shutil.ignore_patterns("figures"))
    rc, out = run_gate(bare)
    assert rc == 0, out
    assert "no analysis/figures" in out


# ------------------------------------------------------------- negatives


def test_svg_content_drift_fails(case_root: Path) -> None:
    svg = case_root / FIGS_REL / f"{NAME}.svg"
    text = svg.read_text(encoding="utf-8")
    svg.write_text(
        text.replace("</svg>", "  <!-- gate7-tamper -->\n</svg>"), encoding="utf-8"
    )
    rc, out = run_gate(case_root)
    assert rc == 1, out
    assert NAME in out
    assert "SVG diff" in out


def test_png_pixel_drift_fails(case_root: Path) -> None:
    """A pixel change outside the stamp rect must fail the PNG leg."""
    from PIL import Image

    png = case_root / FIGS_REL / f"{NAME}.png"
    img = Image.open(png)
    # Far outside STAMP_RECT_PX (24, 24, 480, 270).
    img.putpixel((1000, 700), (255, 0, 0))
    img.save(png, format="PNG")
    rc, out = run_gate(case_root)
    assert rc == 1, out
    assert NAME in out
    assert "PNG" in out


def test_build_head_churn_never_fails(case_root: Path) -> None:
    """The on-disk export is stamped with a real short SHA; the staged
    .git-less build stamps nogit. BUILD-HEAD-only churn is not a drift."""
    record = json.loads((case_root / RECORD_REL).read_text(encoding="utf-8"))
    parsed = _records.parse_stamp(record["stamp"])
    assert parsed is not None
    assert parsed["build_head"] != "nogit", (
        "premise: the committed export carries a real head"
    )
    # No tampering here: this is the pure-churn case, and it must pass.
    rc, out = run_gate(case_root)
    assert rc == 0, out


def test_record_field_drift_fails(case_root: Path) -> None:
    _rewrite_record(
        case_root, lambda d: d["alt_text"].__setitem__("trend", "drifted prose")
    )
    rc, out = run_gate(case_root)
    assert rc == 1, out
    assert NAME in out
    assert "alt_text" in out


def test_vintage_mismatch_fails(case_root: Path) -> None:
    def mutate(doc):
        doc["stamp"] = doc["stamp"].replace("VINTAGE 2026-09", "VINTAGE 2025-12")

    _rewrite_record(case_root, mutate)
    rc, out = run_gate(case_root)
    assert rc == 1, out
    assert NAME in out
    assert "VINTAGE" in out and "2025-12" in out


def test_missing_on_disk_export_fails(case_root: Path) -> None:
    (case_root / FIGS_REL / f"{NAME}.png").unlink()
    rc, out = run_gate(case_root)
    assert rc == 1, out
    assert NAME in out
    assert "missing" in out.lower()


def test_broken_git_dir_is_a_loud_fail(gate7_root: Path) -> None:
    root = gate7_root.parent / "g7git"
    shutil.copytree(gate7_root, root, ignore=shutil.ignore_patterns("figures"))
    (root / ".git").mkdir()  # a .git that is not a git tree
    shutil.copytree(gate7_root / FIGS_REL, root / FIGS_REL)
    rc, out = run_gate(root)
    assert rc == 1
    assert "cannot stage tree" in out
    assert "not a git repository" in out
