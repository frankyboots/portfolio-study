#!/usr/bin/env python3
"""The pipeline's single manifest writer (story 1.5).

The root ``manifest.json`` is written ONLY here, ONLY by the pipeline's
``manifest`` stage (AD-10: build artifacts -> run gates -> stamp HEAD ->
verify tree -> (human) commit), and only after every Edition gate has
passed. It is the machine-readable record that binds one pipeline run:
the AD-9 artifact registry (fields carried verbatim from each artifact
sidecar), the uniform Vintage block cross-checked against the pinned
sha256, the build-input HEAD stamp, and the eight AD-8 gate results.

Deterministic bytes: ``json.dumps(obj, indent=2, sort_keys=True)`` plus
a trailing newline (the sidecar discipline); no wall-clock fields; all
paths are root-relative POSIX. ``build.head`` is ``null`` when the root
is not a git checkout (staged tmp-root test mode). ``edition`` is
``null`` until the first mint (story 1.7: this writer never mints).
``render_registry`` inlines the authored ``web/render_registry.json``
(``[]`` when the file is absent) enforcing the full gate-5 contract at
write time -- gate 5 reads the *previously* committed manifest, so
write-time validation is the only check that sees a first-authored
registry before it lands.

Imported only by ``scripts/pipeline.py``; the analysis layers never
touch the manifest (an assertion test enforces that). Running this file
as a script prints a refusal line and exits 2.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

MANIFEST_NAME = "manifest.json"
SCHEMA_VERSION = "1"

#: AD-9 fields carried verbatim from each sidecar into the registry.
AD9_KEYS: tuple[str, ...] = (
    "name",
    "version",
    "owner",
    "units",
    "index",
    "shape_family",
    "serialization",
)

#: The eight AD-8 gates in AD-8 numbering (not pipeline order), with
#: their runners as root-relative POSIX paths.
GATES: tuple[tuple[int, str, str], ...] = (
    (1, "vintage integrity", "scripts/check_vintage_integrity.py"),
    (2, "validation suite", "analysis/validate_data_md.py"),
    (3, "repro", "scripts/check_repro.py"),
    (4, "accessibility floor", "scripts/check_accessibility_floor.py"),
    (5, "render order", "scripts/check_render_order.py"),
    (6, "cross-doc consistency", "scripts/check_crossdoc_consistency.py"),
    (7, "export freshness", "scripts/check_export_freshness.py"),
    (8, "import wall", "scripts/check_import_walls.py"),
)

SIDECAR_SUFFIX = ".meta.json"
DATA_SUFFIX = ".csv"
RENDER_REGISTRY_REL = ("web", "render_registry.json")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_head(root: Path) -> str | None:
    """Build-input HEAD at stamp time; ``None`` when the root is not a git checkout."""
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,  # intentional: no-git roots are a supported state
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _import_pin(root: Path) -> str:
    """The pinned sha256 (``analysis.series.shiller_io.VINTAGE_SHA256``), imported from ``root``."""
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    from analysis.series import shiller_io

    return shiller_io.VINTAGE_SHA256


def _discover_sidecars(root: Path) -> list[Path]:
    artifacts = root / "artifacts"
    if not artifacts.is_dir():
        return []
    return sorted(artifacts.rglob(f"*{SIDECAR_SUFFIX}"))


def build_registry(
    root: Path,
) -> tuple[dict[str, dict[str, object]], dict[str, object]]:
    """Derive the artifact registry and uniform vintage block from the sidecars.

    Raises ``SystemExit`` naming the offense on: zero sidecars, a
    duplicate registry name, a missing paired data file, a sidecar
    missing an AD-9 key or a valid vintage stamp, non-uniform vintage
    stamps, or a vintage that disagrees with the pin (the writer
    refuses out-of-order/broken states; gate 1 normally pre-empts).
    """
    sidecars = _discover_sidecars(root)
    if not sidecars:
        raise SystemExit(
            f"manifest: no artifact sidecars (*{SIDECAR_SUFFIX}) under {root / 'artifacts'}; "
            "nothing to register"
        )

    vintage: dict[str, object] | None = None
    registry: dict[str, dict[str, object]] = {}
    for sidecar in sidecars:
        rel_meta = sidecar.relative_to(root).as_posix()
        try:
            obj = json.loads(sidecar.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"manifest: {rel_meta} is not valid JSON: {exc}") from exc
        if not isinstance(obj, dict):
            raise SystemExit(f"manifest: {rel_meta} is not a JSON object")
        missing = [k for k in AD9_KEYS if k not in obj]
        if missing:
            raise SystemExit(
                f"manifest: {rel_meta} lacks AD-9 field(s): {', '.join(missing)}"
            )
        stamp = obj.get("vintage")
        if not isinstance(stamp, dict) or not all(
            k in stamp for k in ("sha256", "last_row", "k")
        ):
            raise SystemExit(f"manifest: {rel_meta} carries no valid vintage stamp")
        block: dict[str, object] = {
            "sha256": stamp["sha256"],
            "last_row": stamp["last_row"],
            "k": stamp["k"],
        }
        if vintage is None:
            vintage = block
        elif vintage != block:
            first = str(vintage["sha256"])[:12]
            second = str(block["sha256"])[:12]
            raise SystemExit(
                f"manifest: sidecar vintage stamps disagree ({first}... vs {second}...; "
                f"first offender {rel_meta}); gate 1 (vintage integrity) must pass before the manifest stamps"
            )

        name = obj["name"]
        if not isinstance(name, str):
            raise SystemExit(f"manifest: {rel_meta} 'name' is not a string")
        if name in registry:
            raise SystemExit(
                f"manifest: duplicate registry name {name!r} "
                f"({registry[name]['meta_path']} and {rel_meta})"
            )
        data_file = sidecar.parent / (
            sidecar.name[: -len(SIDECAR_SUFFIX)] + DATA_SUFFIX
        )
        if not data_file.is_file():
            raise SystemExit(
                f"manifest: {rel_meta} pairs with missing data file "
                f"{data_file.relative_to(root).as_posix()}"
            )
        entry: dict[str, object] = {k: obj[k] for k in AD9_KEYS}
        entry.update(
            {
                "data_path": data_file.relative_to(root).as_posix(),
                "meta_path": rel_meta,
                "data_sha256": _sha256_file(data_file),
                "meta_sha256": _sha256_file(sidecar),
            }
        )
        registry[name] = entry

    assert vintage is not None  # guaranteed by the zero-sidecar refusal above
    pin = _import_pin(root)
    if vintage["sha256"] != pin:
        raise SystemExit(
            f"manifest: sidecar vintage {vintage['sha256']} does not match the pinned "
            f"sha256 {pin} (shiller_io.VINTAGE_SHA256); the pin and the sidecars must "
            "agree before the manifest stamps"
        )
    return registry, vintage


def load_render_registry(
    root: Path, artifacts: Mapping[str, object]
) -> list[dict[str, object]]:
    """The authored ``web/render_registry.json`` verbatim; ``[]`` when absent.

    Enforces the full gate-5 contract at write time (story 1.7 D4): a
    list of objects each carrying a unique string ``route``; an
    optional ``depends_on`` list of strings; every dependency present
    in the artifact registry's keys AND matched by an earlier registry
    entry's ``route`` (artifact-declaration entries first). Raises
    ``SystemExit`` naming the offender.
    """
    path = root.joinpath(*RENDER_REGISTRY_REL)
    if not path.is_file():
        return []
    rel = path.relative_to(root).as_posix()
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise SystemExit(f"manifest: {rel} is not valid UTF-8: {exc}") from exc
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"manifest: {rel} is not valid JSON: {exc}") from exc
    if not isinstance(doc, list):
        raise SystemExit(f"manifest: {rel} top level is not a list of entries")
    routes_so_far: list[str] = []
    for i, entry in enumerate(doc):
        if not isinstance(entry, dict) or not isinstance(entry.get("route"), str):
            raise SystemExit(
                f"manifest: {rel}[{i}] is not an object with a string 'route'"
            )
        route = entry["route"]
        if route in routes_so_far:
            raise SystemExit(f"manifest: {rel}[{i}]: duplicate route {route!r}")
        routes_so_far.append(route)
        depends = entry.get("depends_on", [])
        if not isinstance(depends, list) or not all(
            isinstance(dep, str) for dep in depends
        ):
            raise SystemExit(
                f"manifest: {rel}[{i}] ({route!r}): depends_on is not a list of strings"
            )
        for dep in depends:
            if dep not in artifacts:
                raise SystemExit(
                    f"manifest: {rel}[{i}] ({route!r}): depends_on {dep!r} is absent "
                    "from the artifact registry"
                )
            elif dep not in routes_so_far[:-1]:
                raise SystemExit(
                    f"manifest: {rel}[{i}] ({route!r}): depends_on {dep!r} does not "
                    "appear at an earlier registry position"
                )
    return doc


def build_manifest(root: Path, results: Mapping[int, str]) -> dict[str, object]:
    """Assemble the manifest object.

    ``results`` maps every AD-8 gate number 1..8 to its result; the
    writer refuses to build when any gate did not pass (no manifest is
    written or updated when any gate failed).
    """
    wanted = [number for number, _, _ in GATES]
    missing = [n for n in wanted if n not in results]
    failed = sorted(n for n in wanted if n in results and results[n] != "pass")
    if missing or failed:
        raise SystemExit(
            "manifest: refuses to stamp; gate result(s) missing "
            f"{missing} and/or not passing {failed}"
        )
    registry, vintage = build_registry(root)
    render_registry = load_render_registry(root, registry)
    gates: list[dict[str, object]] = []
    for number, name, runner in GATES:
        gates.append(
            {
                "gate": number,
                "name": name,
                "runner": runner,
                "result": results[number],
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "edition": None,
        "vintage": vintage,
        "build": {"head": git_head(root)},
        "artifacts": registry,
        "gates": gates,
        "render_registry": render_registry,
    }


def render_manifest(manifest: dict[str, object]) -> bytes:
    """Deterministic bytes: sidecar discipline (indent=2, sort_keys, trailing newline)."""
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_manifest(root: Path, results: Mapping[int, str]) -> Path:
    """Build and write ``root/manifest.json``; return its path."""
    manifest = build_manifest(root, results)
    path = root / MANIFEST_NAME
    path.write_bytes(render_manifest(manifest))
    return path


if __name__ == "__main__":
    print(
        "manifest.py is the pipeline's single manifest writer (imported by "
        "scripts/pipeline.py); it is not a CLI. Run `uv run python scripts/pipeline.py`.",
        file=sys.stderr,
    )
    sys.exit(2)
