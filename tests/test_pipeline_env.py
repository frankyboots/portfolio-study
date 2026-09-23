"""Pipeline runner envelope tests (NFR3 / deterministic envelope AC).

Machine-checks that ``set_envelope()`` lands every envelope variable in
``os.environ`` with its exact pinned value, and that the runner itself
sets the envelope and passes its import-wall stage.
"""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PIPELINE = REPO_ROOT / "scripts" / "pipeline.py"


def load_pipeline():
    spec = importlib.util.spec_from_file_location("pipeline", PIPELINE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_interpreter_is_python_312() -> None:
    assert sys.version_info[:2] == (3, 12), sys.version


def test_set_envelope_pins_all_vars() -> None:
    import os

    pipeline = load_pipeline()
    pipeline.set_envelope()

    assert os.environ["OPENBLAS_NUM_THREADS"] == "1"
    assert os.environ["TZ"] == "UTC"
    assert os.environ["LC_ALL"] == "C"
    assert os.environ["MPLBACKEND"] == "Agg"

    # Subprocess stages: MPLCONFIGDIR at the committed config directory,
    # whose matplotlibrc pins the same fixed svg.hashsalt.
    mplconfig = Path(os.environ["MPLCONFIGDIR"])
    rc_file = mplconfig / "matplotlibrc"
    assert rc_file.is_file()
    rc_text = rc_file.read_text()
    assert f"svg.hashsalt : {pipeline.SVG_HASHSALT}" in rc_text
    assert "backend : Agg" in rc_text

    # In-process: the rcParam is locked to the same fixed string.
    import matplotlib

    assert matplotlib.rcParams["svg.hashsalt"] == pipeline.SVG_HASHSALT


def test_pipeline_happy_path_exits_zero_with_envelope_and_stage(
    tmp_path: Path,
) -> None:
    # Stage a repo-shaped root with the pipeline's inputs so the real
    # run never writes into the repo's artifacts/ during the test: the
    # series and comparator stages regenerate artifacts under the
    # staged root instead of the checked-out repo.
    staged = tmp_path / "repo"
    for name in ("scripts", "analysis", "config"):
        shutil.copytree(
            REPO_ROOT / name,
            staged / name,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    (staged / "data").mkdir()
    shutil.copy2(REPO_ROOT / "data" / "ie_data.xls", staged / "data" / "ie_data.xls")
    # The ledger: the vintage-integrity stage reads it (latest-entry coverage
    # and override stanzas) and must leave it untouched on a steady tree.
    shutil.copy2(REPO_ROOT / "data" / "RUNLOG.md", staged / "data" / "RUNLOG.md")
    # DATA.md: the suite stage (gate 2) and the cross-doc gate (gate 6) read it.
    shutil.copy2(REPO_ROOT / "data" / "DATA.md", staged / "data" / "DATA.md")

    # No-writes-to-repo property: the repo's ledger, committed artifacts,
    # and manifest are byte-identical after the run (1.3's VG1 lesson).
    repo_runlog_before = (REPO_ROOT / "data" / "RUNLOG.md").read_bytes()
    repo_artifacts_before = {
        p: p.read_bytes()
        for p in sorted((REPO_ROOT / "artifacts").rglob("*"))
        if p.is_file()
    }
    repo_manifest_path = REPO_ROOT / "manifest.json"
    repo_manifest_before = (
        repo_manifest_path.read_bytes() if repo_manifest_path.is_file() else None
    )

    result = subprocess.run(
        [sys.executable, str(staged / "scripts" / "pipeline.py")],
        capture_output=True,
        text=True,
        check=False,  # intentional: the exit code is asserted by this test
    )
    assert result.returncode == 0, result.stderr
    for var in ("OPENBLAS_NUM_THREADS=1", "TZ=UTC", "LC_ALL=C", "MPLBACKEND=Agg"):
        assert var in result.stdout
    for stage in (
        "import-wall",
        "series",
        "comparator",
        "figures",
        "vintage-integrity",
        "suite",
        "repro",
        "accessibility",
        "render-order",
        "cross-doc",
        "export-freshness",
        "manifest",
        "tree-check",
    ):
        assert f"stage '{stage}': OK" in result.stdout, (
            f"missing stage '{stage}' line in:\n{result.stdout}"
        )
    assert "OK: vintage integrity" in result.stdout
    assert "passed, 0 failed" in result.stdout  # gate 2 summary line
    assert "SKIP: no git tree" in result.stdout  # gate 3 on a non-git staged root
    assert "stage 'figures': OK" in result.stdout
    assert "built 1 figure" in result.stdout  # the pilot figure rendered in-process
    assert "tree-check: no .git at root" in result.stdout
    assert "pipeline: all stages OK" in result.stdout

    # The staged manifest: written only by the runner, head null (no .git),
    # AD-8 gate results, full registry from the freshly built sidecars.
    import json

    manifest = json.loads((staged / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "1"
    assert manifest["build"] == {"head": None}
    assert [g["gate"] for g in manifest["gates"]] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert all(g["result"] == "pass" for g in manifest["gates"])
    assert len(manifest["artifacts"]) == 3

    assert (REPO_ROOT / "data" / "RUNLOG.md").read_bytes() == repo_runlog_before
    assert {
        p: p.read_bytes()
        for p in sorted((REPO_ROOT / "artifacts").rglob("*"))
        if p.is_file()
    } == repo_artifacts_before
    manifest_after = (
        repo_manifest_path.read_bytes() if repo_manifest_path.is_file() else None
    )
    assert (
        manifest_after == repo_manifest_before
    )  # the staged run never writes the repo's manifest


def test_failing_stage_returns_code_and_names_stage() -> None:
    import contextlib
    import io

    pipeline = load_pipeline()
    # Isolate the failure path: the real stages are expensive (the repro
    # stage spawns a full staged pipeline; the suite stage runs the
    # validation suite), so the runner loop's failure handling is
    # exercised on its own without re-running them.
    saved = list(pipeline.STAGES)
    try:
        pipeline.STAGES[:] = []
        pipeline.STAGES.append(("broken-test-stage", lambda: 3))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = pipeline.main()
    finally:
        pipeline.STAGES[:] = saved
    assert rc == 3
    assert "FAILED: stage 'broken-test-stage'" in err.getvalue()


def _stage_git_tree(tmp_path: Path) -> Path:
    """A minimal staged root that is a real git repo with one seed commit."""
    staged = tmp_path / "repo"
    (staged / "analysis" / "series").mkdir(parents=True)
    (staged / "analysis" / "series" / "note.py").write_text("X = 1\n", encoding="utf-8")
    (staged / "artifacts" / "series").mkdir(parents=True)
    (staged / "artifacts" / "series" / "thing_v1.csv").write_text(
        "1.0\n", encoding="utf-8"
    )
    (staged / "data").mkdir()
    (staged / "data" / "RUNLOG.md").write_text("seed entry\n", encoding="utf-8")
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
    return staged


def _stage_figures_root(tmp_path: Path) -> Path:
    """A .git-less, manifest-less root with the figure inputs but no exports."""
    staged = tmp_path / "repo"
    for name in ("analysis", "config", "scripts"):
        shutil.copytree(
            REPO_ROOT / name,
            staged / name,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    shutil.copytree(REPO_ROOT / "artifacts" / "series", staged / "artifacts" / "series")
    return staged


#: The driver executed inside the staged root (gate 7's driver pattern);
#: its sys.path[0] is the staged root, so ``analysis.*`` resolves to the
#: staged code. Runs exactly the pipeline figures stage against it.
_FIGURES_STAGE_DRIVER = """\
import importlib.util
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "pipeline_under_test", root / "scripts" / "pipeline.py"
)
pipeline = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(pipeline)
pipeline.REPO_ROOT = root
sys.exit(pipeline.run_figures_stage())
"""


def _run_figures_stage(staged: Path) -> tuple[int, str]:
    """One figures-stage run in a fresh subprocess; (exit code, combined output).

    Subprocess isolation is intentional: driving the stage in-process would
    build a matplotlib figure in this pytest process, and a figure build
    after the envelope tests pinned ``LC_ALL=C`` into ``os.environ``
    re-resolves the C-locale category inside the C extensions and leaves
    the process decoding subprocess output as ASCII thereafter.
    """
    driver = staged / "_figures_stage_driver.py"
    driver.write_text(_FIGURES_STAGE_DRIVER, encoding="utf-8")
    try:
        proc = subprocess.run(
            [sys.executable, str(driver)],
            capture_output=True,
            text=True,
            check=False,  # intentional: the return code is the signal
        )
    finally:
        driver.unlink(missing_ok=True)
    return proc.returncode, proc.stdout + proc.stderr


def test_figures_stage_stamp_churn_suppresses_head_only_diff(tmp_path: Path) -> None:
    """Stamp-churn property: the second run leaves the tree byte-identical.

    Drives the pipeline figures stage three times on one .git-less root.
    The first render resolves BUILD-HEAD as ``nogit``; after a
    manifest.json with a 40-hex ``build.head`` is written, the second
    render's stamp differs in the BUILD-HEAD leg only. The stage must
    exit 0 and the pre-render bytes must be restored for all three
    artifacts. The sanity inverse: a genuine input change is NOT
    suppressed.
    """
    import json

    staged = _stage_figures_root(tmp_path)
    figs = staged / "artifacts" / "figures"
    figure = "rebalance_growth_v1"
    suffixes = (".png", ".svg", ".figure.json")

    rc, out1 = _run_figures_stage(staged)
    assert rc == 0, out1
    assert "first render" in out1
    record1 = json.loads((figs / f"{figure}.figure.json").read_text(encoding="utf-8"))
    assert "BUILD-HEAD nogit" in record1["stamp"]
    pre = {suffix: (figs / f"{figure}{suffix}").read_bytes() for suffix in suffixes}

    # Second render: the manifest now carries a 40-hex build.head, so the
    # BUILD-HEAD leg of the stamp is the only difference between renders.
    head = "ab" * 20
    (staged / "manifest.json").write_text(
        json.dumps({"build": {"head": head}}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rc, out2 = _run_figures_stage(staged)
    assert rc == 0, out2
    assert "churn suppressed" in out2
    for suffix in suffixes:
        assert (figs / f"{figure}{suffix}").read_bytes() == pre[suffix], (
            f"{suffix} was rewritten on a BUILD-HEAD-only difference"
        )

    # Sanity inverse: a real input change must NOT be suppressed.
    monthly = staged / "artifacts" / "series" / "canonical_60_40_monthly_v1.csv"
    lines = monthly.read_text(encoding="utf-8").splitlines()
    date_part, real_part, nominal_part = lines[-1].split(",")
    lines[-1] = f"{date_part},{float(real_part) * 2.0:.2f},{nominal_part}"
    monthly.write_text("\n".join(lines) + "\n", encoding="utf-8")
    rc, out3 = _run_figures_stage(staged)
    assert rc == 0, out3
    assert "re-rendered" in out3
    record3 = json.loads((figs / f"{figure}.figure.json").read_text(encoding="utf-8"))
    assert record3["alt_text"] != record1["alt_text"]
    assert (figs / f"{figure}.figure.json").read_bytes() != pre[".figure.json"]


def test_tree_check_flags_dirty_path_outside_allowlist(tmp_path: Path) -> None:
    import contextlib
    import io

    pipeline = load_pipeline()
    staged = _stage_git_tree(tmp_path)
    (staged / "analysis" / "series" / "note.py").write_text("X = 2\n", encoding="utf-8")
    saved_root = pipeline.REPO_ROOT
    try:
        pipeline.REPO_ROOT = staged  # the stage judges the module-level root
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = pipeline.run_tree_check_stage()
    finally:
        pipeline.REPO_ROOT = saved_root
    assert rc == 1
    assert "analysis/series/note.py" in err.getvalue()
    assert "outside the allowlist" in err.getvalue()


def test_tree_check_allows_manifest_artifacts_and_runlog(tmp_path: Path) -> None:
    import contextlib
    import io

    pipeline = load_pipeline()
    staged = _stage_git_tree(tmp_path)
    staged.joinpath("manifest.json").write_text("{}\n", encoding="utf-8")  # untracked
    (staged / "artifacts" / "series" / "thing_v1.csv").write_text(
        "1.0\n2.0\n", encoding="utf-8"
    )  # modified
    (staged / "data" / "RUNLOG.md").write_text(
        "seed entry\nmore\n", encoding="utf-8"
    )  # modified
    saved_root = pipeline.REPO_ROOT
    try:
        pipeline.REPO_ROOT = staged
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = pipeline.run_tree_check_stage()
    finally:
        pipeline.REPO_ROOT = saved_root
    assert rc == 0, out.getvalue()
    assert "publish commit is a human step" in out.getvalue()
