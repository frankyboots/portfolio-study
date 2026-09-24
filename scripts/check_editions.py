#!/usr/bin/env python3
"""Edition no-overwrite guard (story 1.7 / AD-5, NFR5).

Editions are committed frozen static trees under
``web/editions/{yyyy}[-n]/`` (grammar ``^\\d{4}(-\\d+)?$``; the year is
the mint date, not the data-vintage year). Two rules:

1. Every entry under ``web/editions/`` must be a directory whose name
   matches the grammar. ``web/editions/`` absent or empty is the valid
   zero-edition state and passes (git tracks no empty directories; the
   first mint creates the directory).
2. No path under an edition directory that exists at the base ref may
   be changed at all -- not modified, not deleted, not appended to:
   ``git diff --name-status $BASE_REF...HEAD -- web/editions`` may only
   add paths under NEW edition directories. ``BASE_REF`` comes from
   the ``BASE_REF`` environment variable (CI sets it: the PR base SHA
   on a pull request, the push's ``before`` SHA on a push) -- never a
   second positional argument.

Without a ``.git`` tree, without ``BASE_REF``, or when the base ref is
not obtainable, rule 2 is skipped (structural pass, mirroring gate 5's
cold-start behavior); rule 1 still applies to the on-disk tree.

Mirrors ``scripts/check_render_order.py``: ``main(argv)``, zero args ->
repo root, OK/FAIL one-liners naming offenders, exit 0 pass / 1
violation / 2 usage error.

Usable standalone:
    uv run python scripts/check_editions.py [root]
``<root>`` defaults to the repository root.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

EDITIONS_DIR_NAME = "editions"
EDITION_GRAMMAR_RE = re.compile(r"\A\d{4}(-\d+)?\Z")


def _editions_dir(root: Path) -> Path:
    return root / "web" / EDITIONS_DIR_NAME


def _grammar_violations(root: Path) -> list[str]:
    """On-disk rule 1: every entry under web/editions/ is a grammar-conforming dir."""
    editions = _editions_dir(root)
    if not editions.is_dir():
        return []
    violations: list[str] = []
    for entry in sorted(editions.iterdir()):
        if not (entry.is_dir() and EDITION_GRAMMAR_RE.match(entry.name)):
            violations.append(
                f"web/editions/{entry.name}: not a grammar-conforming edition "
                r"directory (expected ^\d{4}(-\d+)?$)"
            )
    return violations


def _edition_of(path: str) -> str | None:
    """The edition directory name of a web/editions/-relative path, or None."""
    parts = path.split("/")
    if len(parts) >= 4 and parts[0] == "web" and parts[1] == EDITIONS_DIR_NAME:
        return parts[2]
    return None


def _diff_guard_violations(
    root: Path, base_ref: str
) -> tuple[list[str] | None, str | None]:
    """Rule 2 against the base ref.

    Returns ``(violations, note)``; ``violations`` is ``None`` when the
    base ref is not obtainable (structural pass, the note names why).
    """
    proc = subprocess.run(
        ["git", "-C", str(root), "ls-tree", "-r", "--name-only", base_ref, "--", "web"],
        capture_output=True,
        text=True,
        check=False,  # intentional: an unobtainable base ref is a supported state
    )
    if proc.returncode != 0:
        return (
            None,
            f"base ref {base_ref!r} not obtainable ({proc.stderr.strip() or 'git ls-tree failed'})",
        )
    base_editions = {
        edition
        for name in proc.stdout.splitlines()
        if (edition := _edition_of(name)) is not None
    }
    diff = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "diff",
            "--name-status",
            f"{base_ref}...HEAD",
            "--",
            "web/editions",
        ],
        capture_output=True,
        text=True,
        check=False,  # intentional: the return code is the signal
    )
    if diff.returncode != 0:
        raise SystemExit(
            f"check_editions: git diff against base ref {base_ref} failed: "
            f"{diff.stderr.strip()}"
        )
    violations: list[str] = []
    for line in diff.stdout.splitlines():
        if not line.strip():
            continue
        status, *paths = line.split("\t")
        if not paths:
            continue
        letter = status[0]
        # M/T/D/A name the changed path; R/C carry (source, destination) --
        # judge BOTH sides: a rename out of a frozen tree deletes a path,
        # a rename into one appends to it. Only a path under an edition
        # that exists at the base ref is frozen; anything else (a fresh
        # edition directory, or outside web/editions/) is out of scope.
        for side, path in enumerate(paths):
            edition = _edition_of(path)
            if edition is None or edition not in base_editions:
                continue
            is_fresh_add = letter == "A" or (letter in ("R", "C") and side == 1)
            verb = "added" if is_fresh_add else "modified or deleted"
            violations.append(
                f"web/editions/{edition}: {path} was {verb} against base ref "
                f"{base_ref} (editions are frozen; corrections ship as new editions)"
            )
    return violations, None


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

    violations = _grammar_violations(root)

    editions = _editions_dir(root)
    on_disk = (
        sorted(e.name for e in editions.iterdir() if e.is_dir())
        if editions.is_dir()
        else []
    )
    base_ref = os.environ.get("BASE_REF", "").strip()
    guard_note = "no-overwrite guard skipped (no .git tree or no BASE_REF env)"
    if (root / ".git").exists() and base_ref:
        guard, note = _diff_guard_violations(root, base_ref)
        if guard is None:
            guard_note = f"no-overwrite guard skipped ({note})"
        else:
            violations += guard
            guard_note = (
                f"no path under an existing edition changed against base ref {base_ref}"
            )

    if violations:
        for violation in violations:
            print(violation, file=sys.stderr)
        print(
            f"FAIL: editions: {len(violations)} violation(s) "
            "(edition grammar ^\\d{4}(-\\d+)?$; no-overwrite against base ref)",
            file=sys.stderr,
        )
        return 1

    if on_disk:
        print(
            f"OK: editions: {len(on_disk)} grammar-conforming edition dir(s) on disk; "
            f"{guard_note}"
        )
    else:
        print(
            "OK: editions: web/editions/ absent or empty (zero-edition state); "
            f"{guard_note}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
