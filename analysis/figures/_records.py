"""Figure record serialization and the release-stamp string (AD-6).

Every figure export carries a ``*.figure.json`` record next to its
PNG/SVG under ``artifacts/figures/``: the figure name, source artifact
names, canvas px, the per-series style declarations, the alt-text
record (EXPERIENCE.md v1 field set), the measured legibility values,
and the stamp string. Records are deterministic — no wall-clock
fields — so they commit with the exports and survive byte-diff.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

RECORDS_DIR_REL = "artifacts/figures"

#: The stamp content schema (DESIGN.md release-stamp), generated from
#: the build, never hand-typed:
#:   ▮ VINTAGE {YYYY-MM} · BUILD-HEAD {short-sha} · {path/to/build-script}
STAMP_RE = re.compile(
    r"^▮ VINTAGE (?P<vintage>\d{4}-\d{2}) · BUILD-HEAD "
    r"(?P<build_head>[0-9a-f]{7,40}|nogit) · (?P<script>analysis/figures/[a-z0-9_]+\.py)$"
)

#: Builder module names gate 7 may regenerate with (defense on the
#: committed record's ``builder`` field).
BUILDER_RE = re.compile(r"^analysis\.figures\.[a-z0-9_]+$")


def record_path(root: Path, name: str) -> Path:
    """``artifacts/figures/{name}.figure.json`` under the given root."""
    return root / RECORDS_DIR_REL / f"{name}.figure.json"


def stamp_string(vintage: str, build_head: str, script_rel: str) -> str:
    """Assemble the release-stamp string."""
    return f"▮ VINTAGE {vintage} · BUILD-HEAD {build_head} · {script_rel}"


def parse_stamp(stamp: str) -> dict[str, str] | None:
    """Parse a stamp string; None when the shape is not the schema's."""
    match = STAMP_RE.match(stamp)
    return match.groupdict() if match else None


def resolve_build_head(root: Path) -> str:
    """The build-input short SHA, per the frozen chain.

    1. ``git rev-parse --short HEAD`` when the root has a real ``.git``
       tree (the commit the build ran against; a git failure is a loud
       error, not a fallback);
    2. the on-disk root ``manifest.json`` ``build.head`` first seven
       chars, when present and a full 40-hex stamp;
    3. the literal ``nogit`` (staged tmp roots with neither).
    """
    if (root / ".git").exists():
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"cannot read the build-input HEAD at {root}: {proc.stderr.strip()}"
            )
        return proc.stdout.strip()
    manifest = root / "manifest.json"
    if manifest.is_file():
        try:
            doc = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"corrupt manifest.json at {root}: {exc}") from exc
        head = (doc.get("build") or {}).get("head")
        if isinstance(head, str) and re.fullmatch(r"[0-9a-f]{40}", head):
            return head[:7]
    return "nogit"


def resolve_vintage(root: Path) -> str:
    """The uniform committed vintage ``YYYY-MM`` across all sidecars.

    Reads ``vintage.last_row`` (``YYYY.MM``) from every on-disk
    ``artifacts/**/*.meta.json``; all values must agree, else the
    build is in a cross-vintage state and the gate fails loudly.
    """
    sidecars = sorted((root / "artifacts").rglob("*.meta.json"))
    if not sidecars:
        raise RuntimeError(
            f"no sidecars under {root / 'artifacts'} -- nothing to read a vintage from"
        )
    vintages: set[str] = set()
    for sidecar in sidecars:
        doc = json.loads(sidecar.read_text(encoding="utf-8"))
        last_row = (doc.get("vintage") or {}).get("last_row")
        if not isinstance(last_row, str) or not re.fullmatch(r"\d{4}\.\d{2}", last_row):
            raise RuntimeError(
                f"{sidecar.relative_to(root)}: vintage.last_row {last_row!r} is not YYYY.MM"
            )
        vintages.add(last_row[:4] + "-" + last_row[5:])
    if len(vintages) != 1:
        raise RuntimeError(
            f"sidecars disagree on the vintage: {sorted(vintages)} (cross-vintage tree)"
        )
    return vintages.pop()


def serialize_record(record: dict) -> str:
    """The locked record serialization: sort keys, indent 2, trailing newline."""
    return json.dumps(record, indent=2, sort_keys=True) + "\n"


def write_record(root: Path, record: dict) -> Path:
    """Write the record for a figure and return its path."""
    path = record_path(root, str(record["name"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_record(record), encoding="utf-8")
    return path
