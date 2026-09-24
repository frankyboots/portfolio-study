#!/usr/bin/env python3
"""Single-command pipeline runner for the portfolio-study build.

This is the one command every story and CI invokes:
    uv run python scripts/pipeline.py

It (1) asserts the interpreter is Python 3.12, (2) sets the deterministic
runtime envelope itself -- ``OPENBLAS_NUM_THREADS=1``, ``TZ=UTC``,
``LC_ALL=C``, ``MPLBACKEND=Agg``, a locked matplotlib ``svg.hashsalt``
(in-process rcParam, and via a committed ``matplotlibrc`` pointed at by
``MPLCONFIGDIR`` for subprocess stages) -- and (3) runs the ordered
pipeline stages, printing per-stage status. Any stage failure exits
non-zero, naming the failed stage.

Stage order (AD-10): build artifacts -> run gates -> stamp HEAD ->
verify tree -> (human) commit. The ``manifest`` stage is the runner's
single write of the root ``manifest.json`` (via ``scripts/manifest.py``)
and runs only after all eight Edition gates returned 0; no manifest is
written or updated when any gate failed. The runner never commits: the
final ``tree-check`` stage verifies the dirty set against the allowlist
and hands the publish commit to the human (repo commit conventions).
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

#: Fixed string constant; the one hash salt for every SVG export.
SVG_HASHSALT = "portfolio-study-v1"

#: Deterministic runtime envelope the runner sets itself.
ENVELOPE: dict[str, str] = {
    "OPENBLAS_NUM_THREADS": "1",
    "TZ": "UTC",
    "LC_ALL": "C",
    "MPLBACKEND": "Agg",
}


def assert_python_312() -> None:
    """Hard requirement: the pinned environment is Python 3.12."""
    if sys.version_info[:2] != (3, 12):
        raise SystemExit(
            f"pipeline requires Python 3.12 (found {sys.version_info.major}."
            f"{sys.version_info.minor}); run it via `uv run python scripts/pipeline.py`"
        )


def set_envelope() -> None:
    """Set the full deterministic envelope for this process and its children.

    Subprocess matplotlib stages inherit ``MPLCONFIGDIR`` pointing at the
    committed config directory (``config/matplotlibrc``), which pins the
    same ``svg.hashsalt`` set in-process here -- so SVG bytes are
    deterministic whether or not a stage imports matplotlib itself.
    """
    import os

    for key, value in ENVELOPE.items():
        os.environ[key] = value
    os.environ["MPLCONFIGDIR"] = str(REPO_ROOT / "config")

    import matplotlib

    matplotlib.rcParams["svg.hashsalt"] = SVG_HASHSALT


def run_import_wall_check() -> int:
    """Stage: import-wall check (Edition gate 8). Fails the build on any violation."""
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "check_import_walls.py"), str(REPO_ROOT)],
        capture_output=True,
        text=True,
        check=False,  # intentional: the stage's exit code IS the signal
    )
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    return result.returncode


def _run_gate(script_name: str) -> int:
    """Run one Edition-gate CLI as a subprocess against the repo root."""
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script_name), str(REPO_ROOT)],
        capture_output=True,
        text=True,
        check=False,  # intentional: the stage's exit code IS the signal
    )
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    return result.returncode


def run_series_stage() -> int:
    """Stage: build the canonical monthly 60/40 series artifacts.

    Imports the builder in-process; the repo root is prepended to
    ``sys.path`` first so ``analysis.series`` resolves when the runner
    is launched as ``python scripts/pipeline.py`` (which puts
    ``scripts/``, not the repo root, on the path).
    """
    root_str = str(REPO_ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    from analysis.series.canonical_60_40 import build_series

    return build_series(REPO_ROOT)


def run_comparator_stage() -> int:
    """Stage: build the annual-rebalance comparator and diff artifacts.

    Imports the builder in-process; same ``sys.path`` bootstrap as the
    ``series`` stage so ``analysis.series`` resolves when the runner is
    launched as ``python scripts/pipeline.py``.
    """
    root_str = str(REPO_ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    from analysis.series.rebalance_comparator import build_comparator

    return build_comparator(REPO_ROOT)


def run_metrics_stage() -> int:
    """Stage: compute the >=15% drawdown episodes over the canonical real index.

    Imports the metrics builder in-process; same ``sys.path`` bootstrap
    as the ``series``/``comparator`` stages so ``analysis.metrics``
    resolves when the runner is launched as ``python scripts/pipeline.py``.
    """
    root_str = str(REPO_ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    from analysis.metrics.drawdown import build_episodes

    return build_episodes(REPO_ROOT)


def run_figures_stage() -> int:
    """Stage: render the registered figures (after ``comparator``, pre-gates).

    Imports the figure registry in-process; same ``sys.path`` bootstrap
    as the ``series`` stage so ``analysis.figures`` resolves when the
    runner is launched as ``python scripts/pipeline.py``. Each figure's
    pre-render on-disk bytes are captured first, the build runs, and
    the regenerated bytes are judged with the shared non-stamp diff
    (``analysis.figures._diff``): SVG byte-equal with the
    ``release-stamp`` group stripped, PNG pixel-exact outside
    ``STAMP_RECT_PX``, record equal or BUILD-HEAD-leg-only. A
    BUILD-HEAD-only difference never rewrites (the pre-render bytes
    are restored) so unrelated commits leave the tree byte-clean; any
    other difference (content drift, or the record's VINTAGE no longer
    matching the sidecar vintage) keeps the regenerated exports.
    """
    root_str = str(REPO_ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    from analysis.figures import _diff, registry, style

    out_dir = REPO_ROOT / "artifacts" / "figures"

    def fig_bytes(name: str) -> dict[str, bytes | None]:
        def read(suffix: str) -> bytes | None:
            path = out_dir / f"{name}{suffix}"
            return path.read_bytes() if path.is_file() else None

        return {
            "png": read(".png"),
            "svg": read(".svg"),
            "record": read(".figure.json"),
        }

    names = sorted(registry.FIGURE_BUILDERS)
    pre = {name: fig_bytes(name) for name in names}
    rc = registry.build_all(REPO_ROOT)
    if rc != 0:
        return rc
    for name in names:
        old, new = pre[name], fig_bytes(name)
        old_png, old_svg, old_record = old["png"], old["svg"], old["record"]
        new_png, new_svg, new_record = new["png"], new["svg"], new["record"]
        if old_png is None or old_svg is None or old_record is None:
            print(f"figures: {name}: first render (export + record written)")
            continue
        if new_png is None or new_svg is None or new_record is None:
            print(f"figures: {name}: build wrote no exports", file=sys.stderr)
            return 1
        try:
            svg_match = _diff.strip_stamp_groups(new_svg) == _diff.strip_stamp_groups(
                old_svg
            )
        except ValueError as exc:
            print(f"figures: {name}: {exc}", file=sys.stderr)
            return 1
        png_match = _diff.png_equal_outside_rect(old_png, new_png, style.STAMP_RECT_PX)
        record_same = old_record == new_record
        churn_only = _diff.stamps_match_pre_post(old_record, new_record)
        if svg_match and png_match and (record_same or churn_only):
            (out_dir / f"{name}.png").write_bytes(old_png)
            (out_dir / f"{name}.svg").write_bytes(old_svg)
            (out_dir / f"{name}.figure.json").write_bytes(old_record)
            print(
                f"figures: {name}: unchanged "
                f"(BUILD-HEAD-only churn suppressed, pre-render bytes restored)"
                if not record_same
                else f"figures: {name}: byte-identical, no rewrite"
            )
        else:
            print(
                f"figures: {name}: re-rendered (content drift: "
                f"svg-match={svg_match}, png-match={png_match}, "
                f"record-churn-only={churn_only})"
            )
    return 0


def run_vintage_integrity_stage() -> int:
    """Stage: vintage-integrity (after all artifact stages).

    First the LATEST-STALE fallback: when the pin was already updated
    without a recorder run, the missing ledger entry is appended here
    via the shared renderer (the suite subprocess runs only on that
    append path). Then the gate verdict decides: a cross-Vintage mix
    without a logged override fails the build.
    """
    root_str = str(REPO_ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    from analysis import vintage_ledger

    if vintage_ledger.ensure_ledger_covers_vintage(REPO_ROOT):
        print(
            "vintage-integrity: latest ledger entry did not cover the on-disk "
            "vintage; appended the machine entry (suite captured at append time)"
        )
    ok, lines = vintage_ledger.check_vintage_integrity(REPO_ROOT)
    for line in lines:
        print(line, file=sys.stderr if not ok else None)
    return 0 if ok else 1


def run_suite_stage() -> int:
    """Stage: validation suite, Edition gate 2.

    Subprocesses ``analysis/validate_data_md.py`` with the invoking
    process's ``sys.executable`` (the same pinned environment),
    mirroring the import-wall stage pattern.
    """
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "analysis" / "validate_data_md.py")],
        capture_output=True,
        text=True,
        check=False,  # intentional: the stage's exit code IS the signal
    )
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    return result.returncode


def run_repro_stage() -> int:
    """Stage: repro, Edition gate 3 (byte-compare from clean checkout)."""
    return _run_gate("check_repro.py")


def run_accessibility_stage() -> int:
    """Stage: accessibility floor, Edition gate 4 (structural seed, pre-1.6)."""
    return _run_gate("check_accessibility_floor.py")


def run_render_order_stage() -> int:
    """Stage: render order, Edition gate 5 (structural seed; 1.7's contract)."""
    return _run_gate("check_render_order.py")


def run_crossdoc_stage() -> int:
    """Stage: cross-doc consistency, Edition gate 6 (structural seed)."""
    return _run_gate("check_crossdoc_consistency.py")


def run_export_freshness_stage() -> int:
    """Stage: export freshness, Edition gate 7 (structural seed, pre-1.6)."""
    return _run_gate("check_export_freshness.py")


def run_manifest_stage() -> int:
    """Stage: write the root ``manifest.json`` (the runner's single write).

    Runs only after all eight gates returned 0 (AD-10); the writer
    refuses out-of-order/broken states on its own, so a failed gate
    never leaves a manifest written or updated. The stamp is the
    build-input HEAD; a non-git root stamps ``null``.
    """
    for base in (REPO_ROOT, SCRIPTS_DIR):
        base_str = str(base)
        if base_str not in sys.path:
            sys.path.insert(0, base_str)
    import json

    import manifest as manifest_writer

    try:
        path = manifest_writer.write_manifest(REPO_ROOT, gate_results)
    except (
        SystemExit
    ) as exc:  # writer refusal (zero sidecars, mixed stamps, pin drift, ...)
        message = exc.code if isinstance(exc.code, str) else str(exc)
        print(f"manifest: {message}", file=sys.stderr)
        return 1
    doc = json.loads(path.read_text(encoding="utf-8"))
    head = doc["build"]["head"]
    print(
        f"manifest: wrote {path.name} (registry {len(doc['artifacts'])} artifact(s), "
        f"8/8 gates pass, build-input HEAD {head if head is not None else 'null'})"
    )
    return 0


def run_tree_check_stage() -> int:
    """Stage: verify the tree (last stage; the pipeline never commits).

    Without ``.git`` prints a note and exits 0 (staged tmp roots).
    With git, fails (exit 1) if ``git status --porcelain`` shows any
    dirty path outside ``{manifest.json, artifacts/**, data/RUNLOG.md}``,
    naming every offending path; otherwise prints the publish-commit
    instruction (the human commits, per repo commit conventions §5).
    """
    if not (REPO_ROOT / ".git").exists():
        print(
            "tree-check: no .git at root -- tree verification skipped (staged tmp root)"
        )
        return 0
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print(f"tree-check: git status failed: {proc.stderr.strip()}", file=sys.stderr)
        return 1
    allowed: list[str] = []
    offending: list[str] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        target = line[3:]
        if " -> " in target:  # rename: judge the destination
            target = target.rsplit(" -> ", 1)[1]
        if (
            target == "manifest.json"
            or target.startswith("artifacts/")
            or target == "data/RUNLOG.md"
        ):
            allowed.append(target)
        else:
            offending.append(target)
    if offending:
        for path in sorted(set(offending)):
            print(
                f"tree-check: dirty path outside the allowlist: {path}", file=sys.stderr
            )
        print(
            "FAIL: tree-check: commit or revert the paths above before publishing "
            "(allowlist: manifest.json, artifacts/**, data/RUNLOG.md)",
            file=sys.stderr,
        )
        return 1
    print(
        "tree-check: tree clean apart from the allowlist "
        f"({', '.join(sorted(set(allowed))) if allowed else 'nothing dirty'})"
    )
    print(
        "tree-check: the publish commit is a human step -- commit the runner's output "
        "per the repo commit conventions §5; the pipeline never commits."
    )
    return 0


#: Pipeline stage -> AD-8 gate number (the manifest records the eight
#: gates in AD-8 numbering, not pipeline order).
STAGE_TO_GATE: dict[str, int] = {
    "vintage-integrity": 1,
    "suite": 2,
    "repro": 3,
    "accessibility": 4,
    "render-order": 5,
    "cross-doc": 6,
    "export-freshness": 7,
    "import-wall": 8,
}

#: Gate results accumulated during a run (AD-8 number -> result);
#: the manifest stage stamps only when all eight are "pass".
gate_results: dict[int, str] = {}


#: Ordered pipeline stages; later stories append here.
STAGES: list[tuple[str, Callable[[], int]]] = [
    ("import-wall", run_import_wall_check),
    ("series", run_series_stage),
    ("comparator", run_comparator_stage),
    ("metrics", run_metrics_stage),
    ("figures", run_figures_stage),
    ("vintage-integrity", run_vintage_integrity_stage),
    ("suite", run_suite_stage),
    ("repro", run_repro_stage),
    ("accessibility", run_accessibility_stage),
    ("render-order", run_render_order_stage),
    ("cross-doc", run_crossdoc_stage),
    ("export-freshness", run_export_freshness_stage),
    ("manifest", run_manifest_stage),
    ("tree-check", run_tree_check_stage),
]


def main() -> int:
    assert_python_312()
    set_envelope()

    print(f"python {sys.version.split()[0]} | deterministic envelope:")
    import os

    for key in (*ENVELOPE, "MPLCONFIGDIR"):
        print(f"  {key}={os.environ[key]}")
    print(
        f"  svg.hashsalt={SVG_HASHSALT} (rcParam in-process; pinned in config/matplotlibrc)"
    )

    gate_results.clear()
    for name, stage in STAGES:
        try:
            rc = stage()
        except Exception as exc:  # noqa: BLE001 -- any stage crash must name the stage
            print(
                f"FAILED: stage '{name}' raised {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            return 1
        if rc != 0:
            print(f"FAILED: stage '{name}' exited {rc}", file=sys.stderr)
            return rc
        gate_number = STAGE_TO_GATE.get(name)
        if gate_number is not None:
            gate_results[gate_number] = "pass"
        print(f"stage '{name}': OK")
    print("pipeline: all stages OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
