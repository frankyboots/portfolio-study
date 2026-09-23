"""Gate 4 (accessibility floor) staged-root matrix.

The seed rule "committed exports fail" is retired by this story:
committed figure exports are the expected state. Each violation class
of the floor gets one negative on a staged root, and the clean pilot
record passes. Structural checks (usage, zero-arg, git loud-fail,
committed-set semantics) stay in tests/test_gates_scaffold.py.
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
GATE4 = REPO_ROOT / "scripts" / "check_accessibility_floor.py"

RECORD_REL = "artifacts/figures/rebalance_growth_v1.figure.json"


@pytest.fixture(scope="module")
def gate4_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A .git-less repo-shaped root carrying the pilot figure + record on disk."""
    staged = tmp_path_factory.mktemp("gate4") / "repo"
    for name in ("analysis", "config", "artifacts"):
        shutil.copytree(
            REPO_ROOT / name,
            staged / name,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    (staged / "data").mkdir()
    shutil.copy2(REPO_ROOT / "data" / "DATA.md", staged / "data" / "DATA.md")
    assert (staged / RECORD_REL).is_file(), "the pilot record must exist in the repo"
    return staged


_counter = itertools.count()


def run_gate(root: Path) -> tuple[int, str]:
    """(exit code, combined stdout+stderr)."""
    proc = subprocess.run(
        [sys.executable, str(GATE4), str(root)],
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


@pytest.fixture
def gate4_case(gate4_root: Path) -> Path:
    """A throwaway copy of the module root (tamper tests mutate freely)."""
    case = gate4_root.parent / f"case-{next(_counter):02d}"
    shutil.copytree(gate4_root, case)
    return case


# --------------------------------------------------------------- positive


def test_clean_pilot_passes(gate4_case: Path) -> None:
    rc, out = run_gate(gate4_case)
    assert rc == 0, out
    assert "OK: accessibility floor" in out


def test_no_records_is_structural_pass(gate4_case: Path) -> None:
    shutil.rmtree(gate4_case / "artifacts" / "figures")
    rc, out = run_gate(gate4_case)
    assert rc == 0, out
    assert "0 figure record" in out


# ------------------------------------------------------------- structure


def test_missing_matplotlibrc_fails(gate4_case: Path) -> None:
    (gate4_case / "config" / "matplotlibrc").unlink()
    rc, out = run_gate(gate4_case)
    assert rc == 1
    assert "matplotlibrc" in out


def test_contract_ratio_mismatch_fails(gate4_case: Path) -> None:
    contract = gate4_case / "config" / "pairings_contract.json"
    doc = json.loads(contract.read_text(encoding="utf-8"))
    for row in doc["pairings"]:
        if row["fg"] == "ink" and row["on"] == "paper":
            row["ratio"] = 12.0  # recorded ratio no longer matches the recomputed 18.41
    contract.write_text(
        json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    rc, out = run_gate(gate4_case)
    assert rc == 1
    assert "recorded" in out and "recomputed" in out


# ---------------------------------------------------------- record matrix


def test_role_threshold_violation_in_record_fails(gate4_case: Path) -> None:
    """faded/dark recomputes to ~3.78: below the text-normal 4.5 floor."""
    _rewrite_record(
        gate4_case,
        lambda d: d["style_declarations"].append(
            {
                "element": "ghost_caption",
                "fg": "faded",
                "on": "dark",
                "role": "text-normal",
            }
        ),
    )
    rc, out = run_gate(gate4_case)
    assert rc == 1
    assert "rebalance_growth_v1" in out
    assert "faded" in out and "4.5" in out


def test_unknown_pairing_fails(gate4_case: Path) -> None:
    _rewrite_record(
        gate4_case,
        lambda d: d["style_declarations"].append(
            {
                "element": "phantom",
                "fg": "phantom-red",
                "on": "paper",
                "role": "text-normal",
            }
        ),
    )
    rc, out = run_gate(gate4_case)
    assert rc == 1
    assert "phantom-red" in out


def test_missing_alt_field_fails(gate4_case: Path) -> None:
    _rewrite_record(gate4_case, lambda d: d["alt_text"].__setitem__("extremes", ""))
    rc, out = run_gate(gate4_case)
    assert rc == 1
    assert "extremes" in out


def test_unknown_alt_key_fails(gate4_case: Path) -> None:
    _rewrite_record(gate4_case, lambda d: d["alt_text"].__setitem__("caption", "extra"))
    rc, out = run_gate(gate4_case)
    assert rc == 1
    assert "caption" in out


def test_undersized_display_px_fails(gate4_case: Path) -> None:
    def mutate(doc):
        for m in doc["measurements"]:
            if m["class"] == "series-label":
                m["render_px"] = 10.0
                m["display_px"] = 3.125

    _rewrite_record(gate4_case, mutate)
    rc, out = run_gate(gate4_case)
    assert rc == 1
    assert "series-label" in out and "11.0" in out


def test_inconsistent_measurement_fails(gate4_case: Path) -> None:
    """display_px must equal render_px * 0.3125: a stale value fails."""

    def mutate(doc):
        for m in doc["measurements"]:
            if m["element"] == "tick_labels":
                m["render_px"] = 59.41
                m["display_px"] = 99.0

    _rewrite_record(gate4_case, mutate)
    rc, out = run_gate(gate4_case)
    assert rc == 1
    assert "tick_labels" in out


def test_grayscale_luminance_collision_fails(gate4_case: Path) -> None:
    """Two near-luminance data hues must carry distinct dashes."""

    def mutate(doc):
        for s in doc["series"]:
            if s["id"] == "annual_rebalanced_real":
                s["dash"] = "solid"  # same dash as the monthly (primary) series

    _rewrite_record(gate4_case, mutate)
    rc, out = run_gate(gate4_case)
    assert rc == 1
    assert "luminance" in out.lower()


def test_missing_export_fails(gate4_case: Path) -> None:
    (gate4_case / "artifacts" / "figures" / "rebalance_growth_v1.png").unlink()
    rc, out = run_gate(gate4_case)
    assert rc == 1
    assert "export" in out.lower()


def test_orphaned_export_without_record_fails(gate4_case: Path) -> None:
    """An export without a .figure.json record is an unbuilt artifact."""
    figs = gate4_case / "artifacts" / "figures"
    (figs / "retired_v1.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    rc, out = run_gate(gate4_case)
    assert rc == 1
    assert "retired_v1.png" in out
    assert "orphan" in out.lower()


def test_contract_role_claim_below_threshold_fails(gate4_case: Path) -> None:
    """faded/dark recomputes to 3.78: it satisfies text-large (3.0) but not
    text-normal (4.5), so claiming text-normal on the row fails."""
    contract = gate4_case / "config" / "pairings_contract.json"
    doc = json.loads(contract.read_text(encoding="utf-8"))
    for row in doc["pairings"]:
        if row["fg"] == "faded" and row["on"] == "dark":
            row["roles"] = ["text-large", "text-normal"]
    contract.write_text(
        json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    rc, out = run_gate(gate4_case)
    assert rc == 1
    assert "faded" in out and "text-normal" in out


def test_render_px_below_declared_min_px_fails(gate4_case: Path) -> None:
    def mutate(doc):
        for m in doc["measurements"]:
            if m["element"] == "leader_monthly_rebalanced_real":
                m["render_px"] = 0.5  # declared min_px for the element is 1

    _rewrite_record(gate4_case, mutate)
    rc, out = run_gate(gate4_case)
    assert rc == 1
    assert "min_px" in out
