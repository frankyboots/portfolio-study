"""Eight-gate scaffold tests (story 1.5 / AD-8 seed rules).

Covers the CLI mirror contract (usage, bad root, zero-arg default) for
the five new gate CLIs, and for each of gates 4-7: the structural pass
on today's tree and every seed violation from the spec matrix. Gate 5
additionally covers the committed-manifest render-registry contract
(dangling and out-of-order depends_on, non-list registry, missing route).
"""

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE_SCRIPTS = (
    "check_repro.py",
    "check_accessibility_floor.py",
    "check_render_order.py",
    "check_crossdoc_consistency.py",
    "check_export_freshness.py",
)


def run_cli(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / script), *args],
        capture_output=True,
        text=True,
        check=False,  # intentional: exit codes are asserted per test
    )


def git_run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    )


def commit_all(root: Path, message: str = "seed") -> None:
    git_run(root, "init", "-q")
    git_run(root, "config", "user.email", "t@example.com")
    git_run(root, "config", "user.name", "t")
    git_run(root, "add", "-A")
    git_run(root, "commit", "-q", "-m", message)


def stage_minimal(tmp_path: Path) -> Path:
    """A repo-shaped root with the locked config, the six artifacts, and DATA.md."""
    staged = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / "config", staged / "config")
    shutil.copytree(
        REPO_ROOT / "artifacts",
        staged / "artifacts",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    (staged / "data").mkdir()
    shutil.copy2(REPO_ROOT / "data" / "DATA.md", staged / "data" / "DATA.md")
    return staged


# ---------------------------------------------------------------- usage


def test_gate_clis_usage_and_bad_root(tmp_path: Path) -> None:
    for script in GATE_SCRIPTS:
        too_many = run_cli(script, "a", "b")
        assert too_many.returncode == 2
        assert "usage:" in too_many.stderr
        bad_root = run_cli(script, str(tmp_path / "does-not-exist"))
        assert bad_root.returncode == 2
        assert "no such directory" in bad_root.stderr


# ---------------------------------------------------------------- gate 4


def test_gate4_structural_pass(tmp_path: Path) -> None:
    staged = stage_minimal(tmp_path)
    result = run_cli("check_accessibility_floor.py", str(staged))
    assert result.returncode == 0, result.stderr
    assert "OK: accessibility floor" in result.stdout


def test_gate4_committed_export_is_a_seed_violation(tmp_path: Path) -> None:
    staged = stage_minimal(tmp_path)
    (staged / "artifacts" / "series" / "stray.png").write_bytes(b"\x89PNG")
    (staged / "web").mkdir()
    (staged / "web" / "hero.svg").write_text("<svg/>", encoding="utf-8")
    result = run_cli("check_accessibility_floor.py", str(staged))
    assert result.returncode == 1
    assert "artifacts/series/stray.png" in result.stderr
    assert "web/hero.svg" in result.stderr


def test_gate4_missing_matplotlibrc_is_a_violation(tmp_path: Path) -> None:
    staged = stage_minimal(tmp_path)
    (staged / "config" / "matplotlibrc").unlink()
    result = run_cli("check_accessibility_floor.py", str(staged))
    assert result.returncode == 1
    assert "config/matplotlibrc" in result.stderr


def test_gate4_committed_set_via_git_when_git_present(tmp_path: Path) -> None:
    # With a .git tree the on-disk (untracked) export is NOT committed,
    # so the gate passes on the committed set.
    staged = stage_minimal(tmp_path)
    commit_all(staged)
    (staged / "artifacts" / "series" / "untracked.png").write_bytes(b"\x89PNG")
    result = run_cli("check_accessibility_floor.py", str(staged))
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------- gate 5


def test_gate5_no_git_is_structural_pass(tmp_path: Path) -> None:
    staged = stage_minimal(tmp_path)
    result = run_cli("check_render_order.py", str(staged))
    assert result.returncode == 0
    assert "structural pass" in result.stdout


def _commit_manifest(staged: Path, manifest: dict) -> None:
    staged.joinpath("manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    commit_all(staged)


def _manifest(artifacts: dict, registry: object) -> dict:
    return {"schema_version": "1", "artifacts": artifacts, "render_registry": registry}


def test_gate5_empty_committed_registry_is_structural_pass(tmp_path: Path) -> None:
    staged = stage_minimal(tmp_path)
    _commit_manifest(staged, _manifest({"canonical_60_40_monthly_v1": {}}, []))
    result = run_cli("check_render_order.py", str(staged))
    assert result.returncode == 0, result.stderr


def test_gate5_dangling_depends_on_fails(tmp_path: Path) -> None:
    staged = stage_minimal(tmp_path)
    registry = [{"route": "canonical_60_40_monthly_v1", "depends_on": ["ghost_v1"]}]
    _commit_manifest(staged, _manifest({"canonical_60_40_monthly_v1": {}}, registry))
    result = run_cli("check_render_order.py", str(staged))
    assert result.returncode == 1
    assert "ghost_v1" in result.stderr
    assert "absent from the manifest's artifacts keys" in result.stderr


def test_gate5_out_of_order_depends_on_fails(tmp_path: Path) -> None:
    staged = stage_minimal(tmp_path)
    artifacts: dict[str, dict] = {"a_v1": {}, "b_v1": {}, "c_v1": {}}
    # b_v1 at position 1 depends on c_v1, which exists in artifacts but
    # has no earlier registry position.
    registry = [{"route": "a_v1"}, {"route": "b_v1", "depends_on": ["c_v1"]}]
    _commit_manifest(staged, _manifest(artifacts, registry))
    result = run_cli("check_render_order.py", str(staged))
    assert result.returncode == 1
    assert "earlier registry position" in result.stderr


def test_gate5_in_order_depends_on_passes(tmp_path: Path) -> None:
    staged = stage_minimal(tmp_path)
    artifacts: dict[str, dict] = {"a_v1": {}, "b_v1": {}}
    registry = [{"route": "a_v1"}, {"route": "b_v1", "depends_on": ["a_v1"]}]
    _commit_manifest(staged, _manifest(artifacts, registry))
    result = run_cli("check_render_order.py", str(staged))
    assert result.returncode == 0, result.stderr


def test_gate5_non_list_registry_fails(tmp_path: Path) -> None:
    staged = stage_minimal(tmp_path)
    _commit_manifest(staged, _manifest({}, "nope"))
    result = run_cli("check_render_order.py", str(staged))
    assert result.returncode == 1
    assert "not a list" in result.stderr


def test_gate5_entry_without_string_route_fails(tmp_path: Path) -> None:
    staged = stage_minimal(tmp_path)
    _commit_manifest(staged, _manifest({}, [{"route": 1}]))
    result = run_cli("check_render_order.py", str(staged))
    assert result.returncode == 1
    assert "string 'route'" in result.stderr


# ---------------------------------------------------------------- gate 6


def load_crossdoc_module():
    spec = importlib.util.spec_from_file_location(
        "crossdoc_under_test", REPO_ROOT / "scripts" / "check_crossdoc_consistency.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_gate6_no_markdown_is_structural_pass(tmp_path: Path) -> None:
    staged = stage_minimal(tmp_path)
    result = run_cli("check_crossdoc_consistency.py", str(staged))
    assert result.returncode == 0
    assert "structural pass" in result.stdout


def _dataset_line(staged: Path) -> tuple[str, float, str]:
    pin, k, last_row = load_crossdoc_module().parse_pin(staged)
    return pin, k, last_row


def test_gate6_correct_facts_pass(tmp_path: Path) -> None:
    staged = stage_minimal(tmp_path)
    pin, k, last_row = _dataset_line(staged)
    docs = staged / "docs"
    docs.mkdir()
    docs.joinpath("notes.md").write_text(
        f"From the Shiller ie_data pin: sha256: {pin}; K = {k}; last row {last_row}.\n",
        encoding="utf-8",
    )
    result = run_cli("check_crossdoc_consistency.py", str(staged))
    assert result.returncode == 0, result.stderr


def test_gate6_wrong_sha_fails_naming_file_and_line(tmp_path: Path) -> None:
    staged = stage_minimal(tmp_path)
    docs = staged / "docs"
    docs.mkdir()
    docs.joinpath("notes.md").write_text(
        f"first line without facts\nShiller ie_data sha256: {'0' * 64}\n",
        encoding="utf-8",
    )
    result = run_cli("check_crossdoc_consistency.py", str(staged))
    assert result.returncode == 1
    assert "docs/notes.md:2" in result.stderr
    assert "vintage sha256" in result.stderr


def test_gate6_wrong_k_fails(tmp_path: Path) -> None:
    staged = stage_minimal(tmp_path)
    docs = staged / "docs"
    docs.mkdir()
    docs.joinpath("notes.md").write_text(
        "Shiller ie_data K = 999.0\n", encoding="utf-8"
    )
    result = run_cli("check_crossdoc_consistency.py", str(staged))
    assert result.returncode == 1
    assert "K 999.0" in result.stderr


def test_gate6_wrong_last_row_fails(tmp_path: Path) -> None:
    staged = stage_minimal(tmp_path)
    docs = staged / "docs"
    docs.mkdir()
    docs.joinpath("notes.md").write_text(
        "Shiller ie_data last row 2025.01\n", encoding="utf-8"
    )
    result = run_cli("check_crossdoc_consistency.py", str(staged))
    assert result.returncode == 1
    assert "last row 2025.01" in result.stderr


def test_gate6_non_dataset_lines_are_ignored(tmp_path: Path) -> None:
    staged = stage_minimal(tmp_path)
    web = staged / "web"
    web.mkdir()
    web.joinpath("copy.md").write_text(
        "last row 1800.01, K = 1.0, sha256: " + "f" * 64 + "\n",
        encoding="utf-8",
    )
    result = run_cli("check_crossdoc_consistency.py", str(staged))
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------- gate 7


def test_gate7_no_exports_is_structural_pass(tmp_path: Path) -> None:
    staged = stage_minimal(tmp_path)
    result = run_cli("check_export_freshness.py", str(staged))
    assert result.returncode == 0
    assert "OK: export freshness" in result.stdout


def test_gate7_committed_export_fails(tmp_path: Path) -> None:
    staged = stage_minimal(tmp_path)
    (staged / "manual").mkdir()
    (staged / "manual" / "hero.png").write_bytes(b"\x89PNG")
    result = run_cli("check_export_freshness.py", str(staged))
    assert result.returncode == 1
    assert "manual/hero.png" in result.stderr
