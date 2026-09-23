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

    result = subprocess.run(
        [sys.executable, str(staged / "scripts" / "pipeline.py")],
        capture_output=True,
        text=True,
        check=False,  # intentional: the exit code is asserted by this test
    )
    assert result.returncode == 0, result.stderr
    for var in ("OPENBLAS_NUM_THREADS=1", "TZ=UTC", "LC_ALL=C", "MPLBACKEND=Agg"):
        assert var in result.stdout
    assert "stage 'import-wall': OK" in result.stdout
    assert "stage 'series': OK" in result.stdout
    assert "stage 'comparator': OK" in result.stdout
    assert "pipeline: all stages OK" in result.stdout


def test_failing_stage_returns_code_and_names_stage() -> None:
    import contextlib
    import io

    pipeline = load_pipeline()
    pipeline.STAGES.append(("broken-test-stage", lambda: 3))
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        rc = pipeline.main()
    assert rc == 3
    assert "FAILED: stage 'broken-test-stage'" in err.getvalue()
