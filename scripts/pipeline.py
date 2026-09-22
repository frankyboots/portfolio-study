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

Later stories register their stages in ``STAGES`` below; the stage list
is the single ordered flow (no parallel layer builds within one run).
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
    """Stage: import-wall check. Fails the build on any violation."""
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


#: Ordered pipeline stages; later stories append here.
STAGES: list[tuple[str, Callable[[], int]]] = [
    ("import-wall", run_import_wall_check),
    ("series", run_series_stage),
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
        print(f"stage '{name}': OK")
    print("pipeline: all stages OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
