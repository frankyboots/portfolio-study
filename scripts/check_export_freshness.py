#!/usr/bin/env python3
"""Edition gate 7 -- export freshness.

Regenerates every registered figure in a staged tmp root (the committed
``artifacts/**`` + ``config/**`` tree; without a ``.git`` tree the
on-disk tree is staged, so the gate also runs inside a staged root) and
diffs the result against the on-disk exports:

- the SVG diff strips the ``<g id="release-stamp">`` group on both sides
  (the build-only churn stamp); any other byte difference fails,
- the PNG must be pixel-identical outside ``STAMP_RECT_PX``,
- the record is compared with the ``stamp`` field excluded, and each
  record's stamp string must match the full release-stamp format regex
  (checked on BOTH the staged and the on-disk record; a malformed
  BUILD-HEAD or script leg fails even when the VINTAGE token is
  intact), with the record's VINTAGE equal to that side's data-side
  sidecar ``vintage.last_row`` (the ``BUILD-HEAD`` leg may differ
  between sides -- build-only churn, never a failure).

The figure set is enumerated by the staged root's own
``analysis.figures.registry`` (the same single enumeration source the
pipeline ``figures`` stage builds from), run in a subprocess under
``sys.executable`` (the pinned environment). The gate materializes the
staged tree itself -- no full pipeline run.

Any mismatch exits 1 naming the figure and which diff failed. The
pipeline ``figures`` stage and this gate share the registry enumeration
and the ``analysis.figures._diff`` helpers.

Mirrors ``scripts/check_import_walls.py``: ``main(argv)``, zero args ->
repo root, OK/FAIL one-liners naming offenders, exit 0 pass / 1
violation / 2 usage error.

Usable standalone:
    uv run python scripts/check_export_freshness.py [root]
``<root>`` defaults to the repository root.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

RECORD_SUFFIX = ".figure.json"
SVG_BUILD_HEAD_RE = re.compile(r"BUILD-HEAD (\S+)")
STAMP_VINTAGE_RE = re.compile(r"VINTAGE (\d{4}-\d{2})")

#: The driver executed inside the staged tmp root; its sys.path[0] is the
#: staged root itself, so ``analysis.*`` resolves to the staged (committed)
#: code. Writes nothing but the figure exports.
_DRIVER_SOURCE = """\
from pathlib import Path

from analysis.figures import registry

registry.build_all(Path(__file__).resolve().parent)
"""


def _stage_tree(root: Path) -> Path:
    """Materialize the committed tree (or, without a ``.git`` tree, the on-disk
    tree) into a fresh tmp root.

    The full tree is staged -- the figure builders read ``artifacts/**`` and
    ``config/**``, and the driver imports ``analysis.figures`` from the staged
    code itself, mirroring the gate 3 clean-checkout semantics. Figures read
    CSVs, so no ``.xls`` injection is needed. Raises ``OSError``/``ValueError``
    on failure.
    """
    staged = Path(tempfile.mkdtemp(prefix="freshness-gate7-"))
    if (root / ".git").exists():
        tar_path = staged / "tree.tar"
        archive = subprocess.run(
            ["git", "-C", str(root), "archive", "--output", str(tar_path), "HEAD"],
            capture_output=True,
            text=True,
            check=False,  # intentional: the return code is the signal
        )
        if archive.returncode != 0:
            raise ValueError(f"git archive failed: {archive.stderr.strip()}")
        unpack = subprocess.run(
            ["tar", "-xf", str(tar_path), "-C", str(staged)],
            capture_output=True,
            text=True,
            check=False,
        )
        if unpack.returncode != 0:
            raise ValueError(f"tar unpack failed: {unpack.stderr.strip()}")
        tar_path.unlink(missing_ok=True)
    else:
        shutil.copytree(
            root,
            staged,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "_bmad-output"),
            dirs_exist_ok=True,
        )
    return staged


def _stamp_format_violation(record: dict) -> str | None:
    """Violation string, or None, when a record's stamp fails the full AD-6 format.

    The whole stamp string must parse via ``_records.STAMP_RE`` -- not
    just the VINTAGE token: a malformed BUILD-HEAD leg or script path
    is a stamp-format violation even when the VINTAGE is intact.
    """
    from analysis.figures import _records

    stamp = record.get("stamp")
    if not isinstance(stamp, str):
        return "record stamp is missing or not a string"
    if _records.parse_stamp(stamp) is None:
        return f"record stamp {stamp!r} fails the release-stamp format regex"
    return None


def _vintage_violation(record: dict, base: Path) -> str | None:
    """Violation string, or None, for the record-vs-sidecar VINTAGE rule.

    The record's ``VINTAGE`` token must equal the uniform sidecar
    vintage resolved by ``_records.resolve_vintage`` for that tree.
    """
    from analysis.figures import _records

    stamp = record.get("stamp")
    match = STAMP_VINTAGE_RE.search(stamp) if isinstance(stamp, str) else None
    if match is None:
        return "record stamp has no parseable VINTAGE YYYY-MM token"
    try:
        sidecar_vintage = _records.resolve_vintage(base)
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        return f"cannot resolve the sidecar vintage: {exc}"
    if match.group(1) != sidecar_vintage:
        return (
            f"record VINTAGE {match.group(1)!r} != sidecar vintage {sidecar_vintage!r}"
        )
    return None


def _record_diff(staged_record: dict, disk_record: dict) -> str | None:
    """Record comparison: byte-diff with the stamp line treated as equivalent."""
    if set(staged_record) != set(disk_record):
        missing = sorted(set(staged_record) ^ set(disk_record))
        return f"record fields differ (symmetric difference: {', '.join(missing)})"
    for key in sorted(k for k in staged_record if k != "stamp"):
        if staged_record[key] != disk_record[key]:
            return f"record field {key!r} differs"
    return None


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) > 1:
        print(f"usage: {Path(sys.argv[0]).name} [root]", file=sys.stderr)
        return 2
    if argv:
        root = Path(argv[0]).resolve()
    else:
        root = REPO_ROOT
    if not root.is_dir():
        print(f"error: no such directory: {root}", file=sys.stderr)
        return 2

    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    try:
        staged = _stage_tree(root)
    except (OSError, ValueError) as exc:
        print(f"FAIL: export freshness: cannot stage tree: {exc}", file=sys.stderr)
        return 1

    if not (staged / "analysis" / "figures" / "registry.py").is_file():
        print(
            "OK: export freshness: committed tree has no analysis/figures "
            "(no registered figures to check)"
        )
        return 0

    try:
        from analysis.figures import _diff, style
    except ModuleNotFoundError as exc:
        print(
            f"FAIL: export freshness: the staged tree registers figures but "
            f"analysis.figures cannot be imported at {root}: {exc}",
            file=sys.stderr,
        )
        return 1

    # Drop the pre-copied exports: the driver's build must produce them,
    # and an on-disk record that survives staging without a build is a
    # retired leftover (checked below against the on-disk tree).
    shutil.rmtree(staged / "artifacts" / "figures", ignore_errors=True)

    driver = staged / "_gate7_driver.py"
    try:
        driver.write_text(_DRIVER_SOURCE, encoding="utf-8")
        # The deterministic runtime envelope (scripts/pipeline.py's
        # ENVELOPE, mirrored here): the driver must see the same locale,
        # backend, thread and matplotlib-config environment the
        # pipeline pins, whatever the ambient shell carries.
        env = {
            **os.environ,
            "OPENBLAS_NUM_THREADS": "1",
            "TZ": "UTC",
            "LC_ALL": "C",
            "MPLBACKEND": "Agg",
            "MPLCONFIGDIR": str(staged / "config"),
        }
        proc = subprocess.run(
            [sys.executable, str(driver)],
            cwd=str(staged),
            capture_output=True,
            text=True,
            env=env,
            check=False,  # intentional: the exit code is the signal
        )
    finally:
        driver.unlink(missing_ok=True)
    if proc.returncode != 0:
        tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-15:])
        print(tail, file=sys.stderr)
        print(
            f"FAIL: export freshness: staged figure build exited {proc.returncode}",
            file=sys.stderr,
        )
        return 1

    try:
        problems: list[str] = []
        staged_figdir = staged / "artifacts" / "figures"
        disk_figdir = root / "artifacts" / "figures"

        record_paths = sorted(
            p
            for p in (
                staged_figdir.glob(f"*{RECORD_SUFFIX}")
                if staged_figdir.is_dir()
                else []
            )
        )
        if not record_paths:
            print(
                f"FAIL: export freshness: staged build produced no figure records in {staged_figdir}"
            )
            return 1

        for record_path in record_paths:
            name = record_path.name[: -len(RECORD_SUFFIX)]
            where = f"{name}: "
            staged_png, staged_svg = (
                staged_figdir / f"{name}.png",
                staged_figdir / f"{name}.svg",
            )
            disk_png, disk_svg, disk_record = (
                disk_figdir / f"{name}.png",
                disk_figdir / f"{name}.svg",
                disk_figdir / f"{name}{RECORD_SUFFIX}",
            )

            for label, path in (
                ("PNG", disk_png),
                ("SVG", disk_svg),
                ("record", disk_record),
            ):
                if not path.is_file():
                    problems.append(f"{where}missing {label} export ({path.name})")
            if any(not p.is_file() for p in (disk_png, disk_svg, disk_record)):
                continue

            # SVG: strip the stamp group on both sides; the rest must match.
            try:
                new_svg_text = staged_svg.read_text(encoding="utf-8")
                disk_svg_text = disk_svg.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                problems.append(f"{where}SVG unreadable or undecodable: {exc}")
                continue
            if not SVG_BUILD_HEAD_RE.search(new_svg_text):
                problems.append(
                    f"{where}SVG stamp line missing from regenerated export"
                )
            try:
                if _diff.strip_stamp_groups(new_svg_text) != _diff.strip_stamp_groups(
                    disk_svg_text
                ):
                    problems.append(f"{where}SVG diff (stamp group stripped) differs")
            except ValueError as exc:
                problems.append(f"{where}SVG stamp group error: {exc}")

            # PNG: pixel-identical outside the stamp rect.
            try:
                if not _diff.png_equal_outside_rect(
                    staged_png.read_bytes(),
                    disk_png.read_bytes(),
                    style.STAMP_RECT_PX,
                ):
                    problems.append(
                        f"{where}PNG pixels differ outside {style.STAMP_RECT_PX}"
                    )
            except OSError as exc:
                problems.append(f"{where}PNG unreadable: {exc}")

            # Record: fields equal with the stamp excluded; VINTAGE
            # matches the sidecar.
            try:
                staged_record = json.loads(record_path.read_text(encoding="utf-8"))
                disk_record = json.loads(disk_record.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                problems.append(f"{where}record unreadable: {exc}")
                continue
            diff = _record_diff(staged_record, disk_record)
            if diff:
                problems.append(f"{where}{diff}")
            for label, record, base in (
                ("staged", staged_record, staged),
                ("on-disk", disk_record, root),
            ):
                format_violation = _stamp_format_violation(record)
                if format_violation:
                    problems.append(f"{where}{label} record: {format_violation}")
                violation = _vintage_violation(record, base)
                if violation:
                    problems.append(f"{where}{label} record: {violation}")

        # A committed record with no staged build is a retired leftover:
        # the record is accessibility evidence for an export that no
        # longer gets rebuilt, so it cannot stay in the tree silently.
        staged_names = {p.name[: -len(RECORD_SUFFIX)] for p in record_paths}
        disk_records = (
            sorted(p.name for p in disk_figdir.glob(f"*{RECORD_SUFFIX}"))
            if disk_figdir.is_dir()
            else []
        )
        for record_name in disk_records:
            stem = record_name[: -len(RECORD_SUFFIX)]
            if stem not in staged_names:
                problems.append(
                    f"{stem}: committed record {disk_figdir.as_posix()}/{record_name} "
                    "has no staged build (the figure is not in the staged "
                    "registry - retired leftover)"
                )
    finally:
        shutil.rmtree(staged, ignore_errors=True)

    if problems:
        for p in problems:
            print(p, file=sys.stderr)
        print(
            f"FAIL: export freshness: {len(problems)} problem(s) across {len(record_paths)} figure(s)",
            file=sys.stderr,
        )
        return 1
    print(
        f"OK: export freshness: {len(record_paths)} figure(s) regenerated in a staged "
        "tmp root; SVG/PNG/record non-stamp bytes identical to the committed exports"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
