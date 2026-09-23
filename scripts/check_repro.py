#!/usr/bin/env python3
"""Edition gate 3 -- repro (byte-compare from clean checkout).

Archives ``git archive HEAD`` into a temporary root, injects the
working-tree ``data/ie_data.xls`` and ``data/RUNLOG.md`` (both untracked
concerns of the checkout; the latter keeps the inner vintage-integrity
stage steady), runs ``scripts/pipeline.py`` there with the invoking
process's ``sys.executable`` (the same pinned environment), and then
byte-diffs every ``artifacts/**`` file: tmp bytes vs
``git show HEAD:<path>``. Any drift exits 1 naming each drifted path.
The diff universe is ``artifacts/**`` only -- root-level files are never
diffed (the staged tmp root has no ``.git``, so the manifest itself is
never part of the byte-diff).

Without a ``.git`` tree at the root the gate prints
``SKIP: no git tree`` and exits 0 -- this is also the inner staged
run's behavior, closing the self-recursion.

Mirrors ``scripts/check_import_walls.py``: ``main(argv)``, zero args ->
repo root, OK/FAIL one-liners naming offenders, exit 0 pass / 1
violation / 2 usage error.

Usable standalone:
    uv run python scripts/check_repro.py [root]
``<root>`` defaults to the repository root.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


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

    if not (root / ".git").exists():
        print("SKIP: no git tree")
        return 0

    listing = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-tree",
            "-r",
            "--name-only",
            "HEAD",
            "--",
            "artifacts",
        ],
        text=True,
        capture_output=True,
        check=False,  # intentional: the return code is the signal
    )
    if listing.returncode != 0:
        print(
            f"FAIL: repro: cannot list committed artifacts: {listing.stderr.strip()}",
            file=sys.stderr,
        )
        return 1
    committed = [line for line in listing.stdout.splitlines() if line]

    try:
        with tempfile.TemporaryDirectory(prefix="repro-gate3-") as tmp_name:
            tmp = Path(tmp_name)

            tar_path = tmp / "tree.tar"
            archive = subprocess.run(
                ["git", "-C", str(root), "archive", "--output", str(tar_path), "HEAD"],
                capture_output=True,
                text=True,
                check=False,  # intentional: the return code is the signal
            )
            if archive.returncode != 0:
                print(
                    f"FAIL: repro: git archive failed: {archive.stderr.strip()}",
                    file=sys.stderr,
                )
                return 1
            unpack = subprocess.run(
                ["tar", "-xf", str(tar_path), "-C", str(tmp)],
                capture_output=True,
                text=True,
                check=False,
            )
            if unpack.returncode != 0:
                print(
                    f"FAIL: repro: tar unpack failed: {unpack.stderr.strip()}",
                    file=sys.stderr,
                )
                return 1

            data_dir = tmp / "data"
            data_dir.mkdir(exist_ok=True)
            for name in ("ie_data.xls", "RUNLOG.md"):
                src = root / "data" / name
                if src.is_file():
                    shutil.copy2(src, data_dir / name)
            if not (data_dir / "ie_data.xls").is_file():
                print(
                    f"FAIL: repro: {root / 'data' / 'ie_data.xls'} is missing; "
                    "re-pull it per data/RUNLOG.md before running the repro gate",
                    file=sys.stderr,
                )
                return 1

            inner = subprocess.run(
                [sys.executable, str(tmp / "scripts" / "pipeline.py")],
                text=True,
                capture_output=True,
                check=False,  # intentional: the exit code is the signal
            )
            if inner.returncode != 0:
                tail = "\n".join((inner.stdout + inner.stderr).splitlines()[-15:])
                print(tail, file=sys.stderr)
                print(
                    f"FAIL: repro: staged pipeline exited {inner.returncode}",
                    file=sys.stderr,
                )
                return 1

            tmp_files = {
                p.relative_to(tmp).as_posix()
                for p in tmp.joinpath("artifacts").rglob("*")
                if p.is_file()
            }
            drifted: list[str] = []
            for rel in sorted(set(committed) | tmp_files):
                tmp_path = tmp / rel
                tmp_bytes = tmp_path.read_bytes() if tmp_path.is_file() else None
                head = subprocess.run(
                    ["git", "-C", str(root), "show", f"HEAD:{rel}"],
                    capture_output=True,
                    check=False,  # intentional: missing HEAD paths read as absent
                )
                head_bytes = head.stdout if head.returncode == 0 else None
                if tmp_bytes != head_bytes:
                    drifted.append(rel)
            if drifted:
                for rel in drifted:
                    print(f"FAIL: repro drift: {rel}", file=sys.stderr)
                return 1
            print(
                f"OK: repro: {len(set(committed) | tmp_files)} artifact file(s) under artifacts/ "
                "byte-identical between `git archive HEAD` + full pipeline re-run and git HEAD"
            )
            return 0
    except OSError as exc:
        print(f"FAIL: repro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
