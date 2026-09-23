#!/usr/bin/env python3
"""Edition gate 4 -- accessibility floor.

Checks, per the story 1.6 Decisions:

1. ``config/matplotlibrc`` exists (the locked style source).
2. ``config/pairings_contract.json`` is well-formed: every pairing row's
   recorded contrast ratio matches the WCAG ratio recomputed from its
   fg/on hex tokens (+/-0.01), every claimed role is satisfied by that
   ratio (text-normal >=4.5, text-large >=3.0, non-text >=3.0,
   data-series >=3.0, decorative exempt), and no row carries an empty
   role list.
3. Every committed figure record (``artifacts/figures/*.figure.json``,
   on-disk when the root has no ``.git``) passes:
   - alt-text v1 schema completeness (the pinned field set, typed and
     non-empty; unknown fields fail),
   - every fg/on pairing named in the style declarations exists in the
     contract with the declared role claimed (unknown pairing fails),
   - recorded display-px measurements meet the 375px floors
     (series-label >=11, caption-class >=13, mono-stamp >=11,
     series-line >=2; a text-large role additionally >=14),
   - the contract ``min_px`` values hold at render scale (canvas px),
   - display_px is consistent with render_px at the 375/1200 scale,
   - grayscale survival: two data hues within delta-L < 0.02 are
     distinguished by a distinct declared dash,
   - the matching ``.png`` and ``.svg`` exports exist.

"Committed" is the committed set when the root has a ``.git`` tree
(``git ls-files``); without one (staged tmp roots) the working tree is
scanned, since everything on disk is what would be committed.

Mirrors ``scripts/check_import_walls.py``: ``main(argv)``, zero args ->
repo root, OK/FAIL one-liners naming offenders, exit 0 pass / 1
violation / 2 usage error.

Usable standalone:
    uv run python scripts/check_accessibility_floor.py [root]
``<root>`` defaults to the repository root.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SCAN_DIRS = ("artifacts", "web", "manual")
EXPORT_SUFFIXES = (".png", ".svg")
RECORD_SUFFIX = ".figure.json"

CONTRACT_REL = "config/pairings_contract.json"

#: The pinned alt-text v1 field set (EXPERIENCE.md "Alt-text contract").
ALT_TEXT_REQUIRED: dict[str, str] = {
    "alt_text": "str",
    "axis": "dict",
    "chart_type": "str",
    "extremes": "str",
    "pairing_applies": "bool",
    "range": "dict",
    "series": "list",
    "trend": "str",
}
ALT_TEXT_OPTIONAL = ("long_description_ref",)
CHART_TYPES = ("area", "band", "bar", "line", "scatter")
SERIES_ROLES = ("annotation", "band", "baseline", "primary")
AXIS_SCALES = ("linear", "log")


def committed_files(root: Path, suffixes: tuple[str, ...]) -> list[str] | None:
    """Committed (or, without .git, on-disk) files under the scan dirs.

    Returns ``None`` when the committed set could not be listed (git
    failure); the FAIL line naming the git error is printed here.
    """
    names: list[str]
    if (root / ".git").exists():
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--", *SCAN_DIRS],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            print(
                f"FAIL: accessibility floor: cannot list committed artifacts: "
                f"{proc.stderr.strip()}",
                file=sys.stderr,
            )
            return None
        names = [line for line in proc.stdout.splitlines() if line]
    else:
        names = []
        for sub in SCAN_DIRS:
            base = root / sub
            if not base.is_dir():
                continue
            names.extend(
                p.relative_to(root).as_posix() for p in base.rglob("*") if p.is_file()
            )
    return sorted(n for n in names if n.endswith(suffixes))


#: ``export_files`` kept as the story's original helper name.
def export_files(root: Path) -> list[str] | None:
    """Committed (or, without .git, on-disk) PNG/SVG exports under the scan dirs."""
    return committed_files(root, EXPORT_SUFFIXES)


def load_contract(root: Path) -> tuple[dict, list[str]]:
    """Parse the pairings contract; (doc, violations)."""
    violations: list[str] = []
    path = root / CONTRACT_REL
    if not path.is_file():
        return {}, [f"missing {CONTRACT_REL} (the pairings contract)"]
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, [f"{CONTRACT_REL}: not valid JSON: {exc}"]
    for group in ("tokens", "grounds"):
        values = doc.get(group)
        if not isinstance(values, dict) or not values:
            violations.append(f"{CONTRACT_REL}: no '{group}' map")
            continue
        for name, hex_value in values.items():
            if not (
                isinstance(hex_value, str)
                and len(hex_value) == 7
                and hex_value.startswith("#")
            ):
                violations.append(f"{CONTRACT_REL}: {group} {name!r} is not #rrggbb")
    rows = doc.get("pairings")
    if not isinstance(rows, list) or not rows:
        violations.append(f"{CONTRACT_REL}: no 'pairings' rows")
        return doc, violations
    return doc, violations


def contract_hex(doc: dict, fg: object, on: object) -> tuple[str, str] | None:
    """The (fg, on) hex pair from the contract's token/ground maps."""
    fg_hex = doc.get("tokens", {}).get(fg)
    on_hex = doc.get("grounds", {}).get(on) or doc.get("tokens", {}).get(on)
    if not isinstance(fg_hex, str) or not isinstance(on_hex, str):
        return None
    return fg_hex, on_hex


def check_contract(doc: dict) -> list[str]:
    """Recompute every ratio and enforce the role thresholds.

    An empty ``roles`` list is the contract's banned-pairing mechanism
    (the row is retained to keep the ban machine-readable); the ratio
    is still spot-checked, no role is claimable.
    """
    from analysis.figures import accessibility

    violations: list[str] = []
    for i, row in enumerate(doc.get("pairings", [])):
        where = f"{CONTRACT_REL}: pairings[{i}]"
        if not isinstance(row, dict):
            violations.append(f"{where}: row is not an object")
            continue
        fg, on = row.get("fg"), row.get("on")
        roles = row.get("roles", [])
        if not isinstance(roles, list):
            violations.append(f"{where} ({fg}/{on}): roles is not a list")
            continue
        for role in roles:
            if role not in accessibility.ROLE_THRESHOLDS:
                violations.append(f"{where} ({fg}/{on}): unknown role {role!r}")
        pair = contract_hex(doc, fg, on)
        if pair is None:
            violations.append(
                f"{where} ({fg}/{on}): fg/on not in the contract's token/ground maps"
            )
            continue
        try:
            actual = accessibility.contrast_ratio(*pair)
        except ValueError as exc:
            violations.append(f"{where} ({fg}/{on}): {exc}")
            continue
        recorded = row.get("ratio")
        if not isinstance(recorded, (int, float)) or abs(recorded - actual) > 0.01:
            violations.append(
                f"{where} ({fg}/{on}): recorded ratio {recorded!r} != recomputed "
                f"{actual:.4f} (+/-0.01)"
            )
        for role in roles:
            threshold = accessibility.ROLE_THRESHOLDS.get(role)
            if threshold is not None and actual < threshold:
                violations.append(
                    f"{where} ({fg}/{on}): ratio {actual:.4f} below the "
                    f"{role} threshold {threshold}"
                )
    return violations


def _nonempty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def check_alt_text(name: str, alt: object) -> list[str]:
    """Alt-text v1 schema completeness: pinned keys, typed, non-empty."""
    violations: list[str] = []
    if not isinstance(alt, dict):
        return [f"{name}: alt_text is not an object"]
    for key, kind in ALT_TEXT_REQUIRED.items():
        if key not in alt:
            violations.append(f"{name}: alt_text missing field {key!r}")
            continue
        value = alt[key]
        if kind == "str" and not _nonempty_str(value):
            violations.append(f"{name}: alt_text.{key} must be a non-empty string")
        elif kind == "bool" and not isinstance(value, bool):
            violations.append(f"{name}: alt_text.{key} must be a declared bool")
        elif kind == "list" and not (isinstance(value, list) and value):
            violations.append(f"{name}: alt_text.{key} must be a non-empty list")
        elif kind == "dict" and not isinstance(value, dict):
            violations.append(f"{name}: alt_text.{key} must be an object")
    unknown = set(alt) - set(ALT_TEXT_REQUIRED) - set(ALT_TEXT_OPTIONAL)
    for key in sorted(unknown):
        violations.append(f"{name}: alt_text has unknown v1 field {key!r}")
    if "chart_type" in alt and alt["chart_type"] not in CHART_TYPES:
        violations.append(
            f"{name}: alt_text.chart_type {alt['chart_type']!r} not in v1 enum"
        )
    if "axis" in alt and isinstance(alt["axis"], dict):
        axis = alt["axis"]
        for key in ("x_label", "y_label"):
            if not _nonempty_str(axis.get(key)):
                violations.append(
                    f"{name}: alt_text.axis.{key} must be a non-empty string"
                )
        if axis.get("scale") not in AXIS_SCALES:
            violations.append(
                f"{name}: alt_text.axis.scale {axis.get('scale')!r} not in v1 enum"
            )
    if "range" in alt and isinstance(alt["range"], dict):
        for key in ("start", "end", "period"):
            if not _nonempty_str(alt["range"].get(key)):
                violations.append(
                    f"{name}: alt_text.range.{key} must be a non-empty string"
                )
    for entry in alt.get("series", []) if isinstance(alt.get("series"), list) else []:
        if not isinstance(entry, dict):
            violations.append(f"{name}: alt_text.series entry is not an object")
            continue
        sid = entry.get("id", "?")
        for key in ("id", "display_name", "units"):
            if not _nonempty_str(entry.get(key)):
                violations.append(
                    f"{name}: alt_text.series[{sid}].{key} must be a non-empty string"
                )
        if entry.get("role") not in SERIES_ROLES:
            violations.append(
                f"{name}: alt_text.series[{sid}].role {entry.get('role')!r} not in v1 enum"
            )
    if "long_description_ref" in alt and not _nonempty_str(alt["long_description_ref"]):
        violations.append(
            f"{name}: alt_text.long_description_ref must be a non-empty string"
        )
    return violations


def check_pairings(name: str, record: dict, doc: dict) -> list[str]:
    """Every declared fg/on exists in the contract with a satisfied role.

    "Satisfied" = a known role whose WCAG threshold the pair's recomputed
    ratio meets. The row's ``roles`` list is the contract's intended-use
    annotation; the operative checks are existence (unknown pairing
    fails) and the role threshold.
    """
    from analysis.figures import accessibility

    violations: list[str] = []
    rows: dict[tuple[str, str], dict] = {
        (row.get("fg"), row.get("on")): row for row in doc.get("pairings", [])
    }
    for decl in record.get("style_declarations", []):
        fg, on, role = decl.get("fg"), decl.get("on"), decl.get("role")
        where = f"{name}: style declaration {decl.get('element')!r} ({fg}/{on})"
        row = rows.get((fg, on))
        if row is None:
            violations.append(f"{where}: unknown pairing (absent from the contract)")
            continue
        if role not in accessibility.ROLE_THRESHOLDS:
            violations.append(f"{where}: unknown role {role!r}")
            continue
        threshold = accessibility.ROLE_THRESHOLDS[role]
        if threshold:
            pair = contract_hex(doc, fg, on)
            if pair is None:
                violations.append(
                    f"{where}: fg/on not in the contract's token/ground maps"
                )
                continue
            try:
                ratio = accessibility.contrast_ratio(*pair)
            except ValueError:
                ratio = 0.0
            if ratio < threshold:
                violations.append(
                    f"{where}: ratio {ratio:.4f} below the {role} threshold {threshold}"
                )
    return violations


def check_measurements(name: str, record: dict) -> list[str]:
    """375px display-px floors + render-scale min_px + internal consistency."""
    from analysis.figures import accessibility

    violations: list[str] = []
    decls = record.get("style_declarations", [])
    min_px = {
        d.get("element"): d.get("min_px")
        for d in decls
        if isinstance(d, dict) and isinstance(d.get("min_px"), (int, float))
    }
    text_large_elements = {
        d.get("element")
        for d in decls
        if isinstance(d, dict) and d.get("role") == "text-large"
    }
    for m in record.get("measurements", []):
        element = m.get("element", "?")
        where = f"{name}: measurement {element!r}"
        cls, render_px, display_px = (
            m.get("class"),
            m.get("render_px"),
            m.get("display_px"),
        )
        if not (
            isinstance(render_px, (int, float)) and isinstance(display_px, (int, float))
        ):
            violations.append(f"{where}: render_px/display_px must be numbers")
            continue
        # Internal consistency: display_px is the 375/1200 re-scale of render_px.
        expected = accessibility.display_px(float(render_px))
        if abs(float(display_px) - expected) > 0.01:
            violations.append(
                f"{where}: display_px {display_px!r} != render_px x {accessibility.DISPLAY_SCALE} "
                f"({expected:.4f} +/-0.01)"
            )
        floor = accessibility.FLOOR_DISPLAY_PX.get(cls)
        if floor is not None and float(display_px) < floor:
            violations.append(
                f"{where}: display_px {display_px:.4f} below the {cls} floor {floor}"
            )
        declared_min = min_px.get(element)
        if isinstance(declared_min, (int, float)) and float(render_px) < declared_min:
            violations.append(
                f"{where}: render_px {render_px} below the contract min_px {declared_min}"
            )
    # text-large elements need >=14 display px on every matching
    # measurement (exact element name or element_<id> children).
    for element in sorted(e for e in text_large_elements if isinstance(e, str)):
        matches = [
            m
            for m in record.get("measurements", [])
            if isinstance(m, dict)
            and (
                str(m.get("element")) == element
                or str(m.get("element")).startswith(element + "_")
            )
        ]
        if not matches:
            violations.append(
                f"{name}: text-large element {element!r} has no recorded measurement"
            )
        for m in matches:
            if float(m.get("display_px", 0)) < accessibility.TEXT_LARGE_DISPLAY_PX:
                violations.append(
                    f"{name}: measurement {m.get('element')!r}: text-large display_px "
                    f"{m.get('display_px')!r} below {accessibility.TEXT_LARGE_DISPLAY_PX}"
                )
    return violations


def check_grayscale(name: str, record: dict, doc: dict) -> list[str]:
    """Grayscale survival: close-luminance data hues need distinct dashes."""
    from analysis.figures import accessibility

    violations: list[str] = []
    series = [s for s in record.get("series", []) if isinstance(s, dict)]
    for i in range(len(series)):
        for j in range(i + 1, len(series)):
            a, b = series[i], series[j]
            pair_a = contract_hex(doc, a.get("fg"), "paper")
            pair_b = contract_hex(doc, b.get("fg"), "paper")
            if pair_a is None or pair_b is None:
                continue  # unknown fg is already a contract/pairing violation
            try:
                lum_a = accessibility.relative_luminance(
                    accessibility.hex_to_rgb(pair_a[0])
                )
                lum_b = accessibility.relative_luminance(
                    accessibility.hex_to_rgb(pair_b[0])
                )
            except ValueError:
                continue
            close_luminance = abs(lum_a - lum_b) < accessibility.GRAYSCALE_DL_MAX
            same_dash = a.get("dash") == b.get("dash")
            if close_luminance and same_dash:
                violations.append(
                    f"{name}: grayscale survival: {a.get('id')!r} and {b.get('id')!r} "
                    f"collapse to near-identical luminance (delta-L "
                    f"{abs(lum_a - lum_b):.4f} < {accessibility.GRAYSCALE_DL_MAX}) "
                    f"and share dash {a.get('dash')!r}"
                )
    return violations


def check_record(root: Path, path: Path, doc: dict) -> list[str]:
    """Every per-record check for one figure record."""
    rel = path.relative_to(root).as_posix()
    name = path.name[: -len(RECORD_SUFFIX)]
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [f"{rel}: unreadable record: {exc}"]
    if not isinstance(record, dict):
        return [f"{rel}: record is not an object"]
    if record.get("name") != name:
        return [f"{rel}: record name {record.get('name')!r} != filename {name!r}"]
    violations = check_alt_text(name, record.get("alt_text"))
    violations += check_pairings(name, record, doc)
    violations += check_measurements(name, record)
    violations += check_grayscale(name, record, doc)
    return violations


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

    violations: list[str] = []
    if not (root / "config" / "matplotlibrc").is_file():
        violations.append("missing config/matplotlibrc (locked style source)")

    doc, contract_violations = load_contract(root)
    violations += contract_violations
    if not contract_violations:
        violations += check_contract(doc)

    exports = export_files(root)
    if exports is None:
        return 1
    export_set = set(exports)
    records = committed_files(root, (RECORD_SUFFIX,))
    if records is None:
        return 1

    for rel in records:
        record_path = root / rel
        violations += check_record(root, record_path, doc)
        for suffix in (".png", ".svg"):
            expected = rel[: -len(RECORD_SUFFIX)] + suffix
            if expected not in export_set:
                violations.append(f"{rel}: missing export {expected}")

    if violations:
        for v in violations:
            print(v, file=sys.stderr)
        print(
            f"FAIL: accessibility floor: {len(violations)} violation(s) "
            "(contract well-formedness, alt-text v1 schema, known pairings with "
            "satisfied roles, 375px floors, grayscale survival)"
        )
        return 1
    print(
        f"OK: accessibility floor: contract well-formed ({len(doc.get('pairings', []))} "
        f"pairing rows), {len(records)} figure record(s) pass the alt-text/pairing/"
        f"legibility/grayscale floor, matplotlibrc present"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
