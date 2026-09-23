"""Manifest writer tests (story 1.5 / AD-1, AD-9, AD-10).

Covers the manifest schema, the AD-9 registry derived verbatim from the
committed sidecars, determinism, the builder's refusals (zero sidecars,
non-uniform vintage stamps, pin drift, gates not all passing), the
git-HEAD stamp (including head-null on a non-git root), the script-run
refusal (exit 2), and the no-analysis-writer assertion.
"""

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PY = REPO_ROOT / "scripts" / "manifest.py"

PASS_RESULTS = {n: "pass" for n in range(1, 9)}
AD9_KEYS = {
    "name",
    "version",
    "owner",
    "units",
    "index",
    "shape_family",
    "serialization",
}
ENTRY_KEYS = AD9_KEYS | {"data_path", "meta_path", "data_sha256", "meta_sha256"}
PIN = pytest.importorskip("analysis.series.shiller_io").VINTAGE_SHA256


def load_manifest_module():
    spec = importlib.util.spec_from_file_location("manifest_under_test", MANIFEST_PY)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def stage_root(tmp_path: Path) -> Path:
    """A repo-shaped staged root: no .git, pinned dataset, real sidecars."""
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


def test_manifest_schema_and_registry(tmp_path: Path) -> None:
    m = load_manifest_module()
    staged = stage_root(tmp_path)
    manifest = m.build_manifest(staged, PASS_RESULTS)

    assert set(manifest) == {
        "schema_version",
        "edition",
        "vintage",
        "build",
        "artifacts",
        "gates",
        "render_registry",
    }
    assert manifest["schema_version"] == "1"
    assert manifest["edition"] is None  # inert until 1.7
    assert manifest["render_registry"] == []  # inert until 1.7/1.8
    assert manifest["build"] == {"head": None}  # staged root: no .git
    assert manifest["vintage"] == {"sha256": PIN, "last_row": "2026.09", "k": 333.8925}

    gates = manifest["gates"]
    assert [g["gate"] for g in gates] == [1, 2, 3, 4, 5, 6, 7, 8]
    for gate in gates:
        assert set(gate) == {"gate", "name", "runner", "result"}
        assert gate["result"] == "pass"
    runners = {g["gate"]: g["runner"] for g in gates}
    assert runners == {
        1: "scripts/check_vintage_integrity.py",
        2: "analysis/validate_data_md.py",
        3: "scripts/check_repro.py",
        4: "scripts/check_accessibility_floor.py",
        5: "scripts/check_render_order.py",
        6: "scripts/check_crossdoc_consistency.py",
        7: "scripts/check_export_freshness.py",
        8: "scripts/check_import_walls.py",
    }

    artifacts = manifest["artifacts"]
    assert len(artifacts) == 3  # the three pinned series files (AD-9 registry)
    for name, entry in artifacts.items():
        assert set(entry) == ENTRY_KEYS
        assert entry["name"] == name
        sidecar = json.loads((staged / str(entry["meta_path"])).read_text("utf-8"))
        for key in AD9_KEYS:
            assert entry[key] == sidecar[key]  # verbatim from the sidecar
        data = staged / str(entry["data_path"])
        assert data.is_file()
        assert entry["data_sha256"] == hashlib.sha256(data.read_bytes()).hexdigest()
        meta = staged / str(entry["meta_path"])
        assert entry["meta_sha256"] == hashlib.sha256(meta.read_bytes()).hexdigest()
        assert entry["meta_path"].endswith(".meta.json")
        assert not any(key in entry for key in ("row_count", "summary", "vintage"))


def test_manifest_bytes_byte_identical_across_repeated_runs(tmp_path: Path) -> None:
    m = load_manifest_module()
    staged = stage_root(tmp_path)
    path = m.write_manifest(staged, PASS_RESULTS)
    first = path.read_bytes()
    m.write_manifest(staged, PASS_RESULTS)
    assert path.read_bytes() == first  # deterministic: no wall-clock, sorted keys
    json.loads(first)  # valid JSON
    assert first.endswith(b"}\n")


def test_manifest_zero_sidecars_refuses(tmp_path: Path) -> None:
    m = load_manifest_module()
    staged = stage_root(tmp_path)
    shutil.rmtree(staged / "artifacts")
    with pytest.raises(SystemExit, match="no artifact sidecars"):
        m.build_manifest(staged, PASS_RESULTS)


def test_manifest_mixed_vintage_stamps_refuse(tmp_path: Path) -> None:
    m = load_manifest_module()
    staged = stage_root(tmp_path)
    meta = staged / "artifacts" / "series" / "canonical_60_40_annual_v1.meta.json"
    doc = json.loads(meta.read_text("utf-8"))
    doc["vintage"]["sha256"] = "ab" * 32
    meta.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", "utf-8")
    with pytest.raises(SystemExit, match="stamps disagree"):
        m.build_manifest(staged, PASS_RESULTS)


def test_manifest_pin_mismatch_refuses(tmp_path: Path) -> None:
    m = load_manifest_module()
    staged = stage_root(tmp_path)
    for meta in (staged / "artifacts").rglob("*.meta.json"):
        doc = json.loads(meta.read_text("utf-8"))
        doc["vintage"]["sha256"] = "cd" * 32  # uniform, but not the pin
        meta.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", "utf-8")
    with pytest.raises(SystemExit, match="does not match the pinned"):
        m.build_manifest(staged, PASS_RESULTS)


def test_manifest_head_stamp_is_git_head_when_checkout(tmp_path: Path) -> None:
    m = load_manifest_module()
    staged = stage_root(tmp_path)
    for args in (
        ["init", "-q"],
        ["config", "user.email", "t@example.com"],
        ["config", "user.name", "t"],
        ["add", "-A"],
        ["commit", "-q", "-m", "seed"],
    ):
        subprocess.run(
            ["git", "-C", str(staged), *args], check=True, capture_output=True
        )
    head = subprocess.run(
        ["git", "-C", str(staged), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    manifest = m.build_manifest(staged, PASS_RESULTS)
    assert manifest["build"]["head"] == head


def test_manifest_refuses_when_a_gate_did_not_pass(tmp_path: Path) -> None:
    m = load_manifest_module()
    staged = stage_root(tmp_path)
    failing = dict(PASS_RESULTS)
    failing[3] = "fail"
    with pytest.raises(SystemExit, match="refuses to stamp"):
        m.write_manifest(staged, failing)
    missing = {n: "pass" for n in range(1, 8)}  # gate 8 missing
    with pytest.raises(SystemExit, match="refuses to stamp"):
        m.build_manifest(staged, missing)


def test_manifest_script_run_is_a_refusal_exit_two() -> None:
    result = subprocess.run(
        [sys.executable, str(MANIFEST_PY)],
        capture_output=True,
        text=True,
        check=False,  # intentional: exit 2 is asserted
    )
    assert result.returncode == 2
    combined = result.stdout + result.stderr
    assert "not a CLI" in combined


def test_no_analysis_module_touches_the_manifest() -> None:
    offenders = []
    for path in sorted(REPO_ROOT.glob("analysis/**/*.py")):
        rel_parts = path.relative_to(REPO_ROOT).parts
        if "_archive" in rel_parts:
            continue
        if "manifest.json" in path.read_text(encoding="utf-8"):
            offenders.append("/".join(rel_parts))
    assert not offenders, f"analysis/ module(s) touching manifest.json: {offenders}"
