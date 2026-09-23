#!/usr/bin/env python3
"""Edition gate 5 -- scorecard-before-narrative render ordering
(structural seed; the read contract story 1.7 consumes).

Reads the COMMITTED manifest via ``git show HEAD:manifest.json`` --
never the working-tree file, because gates run before the manifest
stage and the tree may carry a not-yet-committed stamp from the
previous run. Without a ``.git`` tree, or when no manifest is committed
yet (cold start), the gate is a structural pass.

Contract on the committed manifest's ``render_registry``:

- it must be a list;
- each entry an object with ``route`` (string);
- optional ``depends_on`` (list of artifact names): every name must be
  present in that manifest's ``artifacts`` keys, and the entry's own
  position must not precede its dependency's (the dependency must occur
  earlier in the registry);
- an empty registry is a structural pass.

Mirrors ``scripts/check_import_walls.py``: ``main(argv)``, zero args ->
repo root, OK/FAIL one-liners naming offenders, exit 0 pass / 1
violation / 2 usage error.

Usable standalone:
    uv run python scripts/check_render_order.py [root]
``<root>`` defaults to the repository root.
"""

from __future__ import annotations

import json
import subprocess
import sys
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
        print("OK: render order: no git tree -- structural pass")
        return 0
    proc = subprocess.run(
        ["git", "-C", str(root), "show", "HEAD:manifest.json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print("OK: render order: no committed manifest.json at HEAD -- structural pass")
        return 0

    try:
        manifest = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        print(
            f"FAIL: render order: committed manifest.json is not valid JSON: {exc}",
            file=sys.stderr,
        )
        return 1
    if not isinstance(manifest, dict):
        print(
            "FAIL: render order: committed manifest.json is not a JSON object",
            file=sys.stderr,
        )
        return 1
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        print(
            "FAIL: render order: committed manifest.json has no artifacts object",
            file=sys.stderr,
        )
        return 1
    registry = manifest.get("render_registry")
    if not isinstance(registry, list):
        print(
            "FAIL: render order: committed manifest render_registry is not a list",
            file=sys.stderr,
        )
        return 1
    if not registry:
        print(
            "OK: render order: committed manifest render_registry is empty -- structural pass"
        )
        return 0

    violations: list[str] = []
    for i, entry in enumerate(registry):
        if not isinstance(entry, dict) or not isinstance(entry.get("route"), str):
            violations.append(
                f"render_registry[{i}] is not an object with a string 'route'"
            )
            continue
        route = entry["route"]
        depends = entry.get("depends_on", [])
        if not isinstance(depends, list) or not all(
            isinstance(d, str) for d in depends
        ):
            violations.append(
                f"render_registry[{i}] ({route!r}): depends_on is not a list of strings"
            )
            continue
        for dep in depends:
            if dep not in artifacts:
                violations.append(
                    f"render_registry[{i}] ({route!r}): depends_on {dep!r} is absent from the "
                    "manifest's artifacts keys"
                )
            elif not any(
                isinstance(prev, dict) and prev.get("route") == dep
                for prev in registry[:i]
            ):
                violations.append(
                    f"render_registry[{i}] ({route!r}): depends_on {dep!r} does not appear at an "
                    "earlier registry position"
                )
    if violations:
        for v in violations:
            print(v, file=sys.stderr)
        print(
            "FAIL: render order: committed manifest render_registry violates the "
            "order-declared contract (route strings; depends_on within artifacts and earlier positions)",
            file=sys.stderr,
        )
        return 1
    print(
        f"OK: render order: committed manifest render_registry has {len(registry)} entry(ies); "
        "all routes strings, all depends_on within artifacts and at earlier positions"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
