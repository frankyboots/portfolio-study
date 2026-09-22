#!/usr/bin/env python3
"""AST import-wall checker for the analysis layer packages.

Scans exactly the four layer packages under ``<root>/analysis/``:
``series``, ``metrics``, ``figures``, ``studio``. Nothing else is
scanned -- ``analysis/validate_data_md.py``, ``analysis/_archive/``,
and ``tests/`` are outside the scan set by construction.

Layer rank: ``series < metrics < figures < studio``. A source module
may only reference lower-ranked layers. The following are checked:

  a. ``upward-import``          -- absolute ``analysis.<higher>.`` imports
                                   (Import / absolute ImportFrom only;
                                   relative imports are not scanned).
  b. ``upward-path-literal``    -- string literals naming a higher layer's
                                   path (``analysis[/\\]<layer>``); docstrings
                                   are excluded from this rule so the
                                   mandated contract docstrings stay clean.
  c. ``upward-subprocess``      -- subprocess call arguments
                                   (subprocess.run / Popen / call /
                                   check_call / check_output) referencing a
                                   higher layer's path.
  d. ``xlrd-outside-series``    -- any xlrd import in a layer other than
                                   ``series`` (sole owner of xlrd I/O).

Every violation is reported as ``file:line: rule: detail``. The exit code
is 1 if any violation was found, 0 otherwise. A file that cannot be read
as UTF-8 or parsed is itself reported as a ``scan-error`` violation and
the scan continues with the remaining files.

Usable standalone:
    uv run python scripts/check_import_walls.py [root]
``<root>`` defaults to the repository root; any root is scanned under
``<root>/analysis/<layer>/``.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

LAYER_RANK: dict[str, int] = {"series": 0, "metrics": 1, "figures": 2, "studio": 3}
LAYER_DIR_RE = re.compile(
    r"analysis[/\\](series|metrics|figures|studio)(?![A-Za-z0-9])"
)

#: subprocess call names that spawn child processes.
_SUBPROCESS_FUNCS = {"run", "Popen", "call", "check_call", "check_output"}


class Violation:
    __slots__ = ("detail", "line", "path", "rule")

    def __init__(self, path: str, line: int, rule: str, detail: str) -> None:
        self.path = path
        self.line = line
        self.rule = rule
        self.detail = detail

    def format(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.detail}"


def _higher_layer_match(literal: str, source_layer: str) -> str | None:
    """Return the higher-layer name if a literal names a higher layer's path."""
    source_rank = LAYER_RANK[source_layer]
    for m in LAYER_DIR_RE.finditer(literal):
        layer = m.group(1)
        if LAYER_RANK[layer] > source_rank:
            return layer
    return None


def check_file(file_path: Path, root: Path) -> list[Violation]:
    source_layer = file_path.relative_to(root).parts[1]
    source_rank = LAYER_RANK[source_layer]
    rel = file_path.relative_to(root).as_posix()
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except (UnicodeDecodeError, SyntaxError) as exc:
        line = getattr(exc, "lineno", 0) or 0
        return [Violation(rel, line, "scan-error", f"{type(exc).__name__}: {exc}")]

    violations: list[Violation] = []

    # Docstring constants are excluded from the path-literal rule.
    docstring_ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                body = node.body[0]
                const = body.value if isinstance(body, ast.Expr) else body
                if isinstance(const, ast.Constant) and const.value == doc:
                    docstring_ids.add(id(const))

    # Subprocess module aliases, per import style.
    subprocess_module_names: set[str] = set()  # for `import subprocess [as X]`
    subprocess_func_names: set[str] = (
        set()
    )  # local names from `from subprocess import ...`
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess":
                    subprocess_module_names.add(alias.asname or alias.name)
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module == "subprocess"
            and node.level == 0
        ):
            for alias in node.names:
                if alias.name in _SUBPROCESS_FUNCS:
                    subprocess_func_names.add(alias.asname or alias.name)

    for node in ast.walk(tree):
        # (a) imports and (d) xlrd outside series.
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            targets: list[tuple[str, int]] = []
            if isinstance(node, ast.Import):
                for alias in node.names:
                    targets.append((alias.name, node.lineno))
            elif node.level == 0 and node.module:  # absolute only; relative not scanned
                base = node.module
                if base == "analysis" or base.startswith("analysis."):
                    parts = base.split(".")
                    target = parts[1] if len(parts) > 1 else None
                    if target in LAYER_RANK:
                        targets.append((f"analysis.{target}", node.lineno))
                    for alias in node.names:
                        if base == "analysis" and alias.name in LAYER_RANK:
                            targets.append((f"analysis.{alias.name}", node.lineno))
                else:
                    targets.append((base, node.lineno))
            for mod, line in targets:
                top = mod.split(".", 1)[0]
                if top == "xlrd" and source_layer != "series":
                    violations.append(
                        Violation(
                            rel,
                            line,
                            "xlrd-outside-series",
                            f"'{mod}' is imported in layer '{source_layer}', but only "
                            f"'analysis.series' may import xlrd",
                        )
                    )
                m = re.match(r"analysis\.([a-z]+)", mod)
                if (
                    m
                    and m.group(1) in LAYER_RANK
                    and LAYER_RANK[m.group(1)] > source_rank
                ):
                    violations.append(
                        Violation(
                            rel,
                            line,
                            "upward-import",
                            f"imports '{mod}' (layer '{m.group(1)}', rank "
                            f"{LAYER_RANK[m.group(1)]}) from layer '{source_layer}' "
                            f"(rank {source_rank}); dependencies may point downward only",
                        )
                    )

        # (b) string literals naming a higher layer's path (docstrings excluded).
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstring_ids:
                continue
            layer = _higher_layer_match(node.value, source_layer)
            if layer is not None:
                violations.append(
                    Violation(
                        rel,
                        node.lineno,
                        "upward-path-literal",
                        f"string literal references path of layer '{layer}' "
                        f"(rank {LAYER_RANK[layer]}) from layer '{source_layer}' "
                        f"(rank {source_rank}); dependencies may point downward only",
                    )
                )

        # (c) subprocess call arguments referencing a higher layer's path.
        if isinstance(node, ast.Call):
            func = node.func
            is_subprocess_call = False
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                is_subprocess_call = (
                    func.value.id in subprocess_module_names
                    or func.value.id == "subprocess"
                ) and func.attr in _SUBPROCESS_FUNCS
            elif isinstance(func, ast.Name):
                is_subprocess_call = func.id in subprocess_func_names
            if is_subprocess_call:
                for arg in ast.walk(node):
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        layer = _higher_layer_match(arg.value, source_layer)
                        if layer is not None:
                            violations.append(
                                Violation(
                                    rel,
                                    node.lineno,
                                    "upward-subprocess",
                                    f"subprocess call references path of layer '{layer}' "
                                    f"(rank {LAYER_RANK[layer]}) from layer '{source_layer}' "
                                    f"(rank {source_rank}); dependencies may point downward only",
                                )
                            )
    return violations


def scan_root(root: Path) -> tuple[list[Violation], int]:
    """Scan the layer packages under ``root``; return (violations, layers scanned)."""
    violations: list[Violation] = []
    layers_scanned = 0
    for layer in LAYER_RANK:
        layer_dir = root / "analysis" / layer
        if not layer_dir.is_dir():
            continue
        layers_scanned += 1
        for py_file in sorted(layer_dir.rglob("*.py")):
            violations.extend(check_file(py_file, root))
    return violations, layers_scanned


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) > 1:
        print(f"usage: {Path(sys.argv[0]).name} [root]", file=sys.stderr)
        return 2
    if argv:
        root = Path(argv[0]).resolve()
    else:
        # Default root: the repository (parent of this script's directory).
        root = Path(__file__).resolve().parent.parent
    if not (root / "analysis").is_dir():
        print(f"error: no 'analysis/' directory under {root}", file=sys.stderr)
        return 2

    violations, layers_scanned = scan_root(root)
    if violations:
        for v in violations:
            print(v.format(), file=sys.stderr)
        print(
            f"FAIL: {len(violations)} import-wall violation(s) in {root / 'analysis'} "
            f"(layer rank: series < metrics < figures < studio; downward only)",
            file=sys.stderr,
        )
        return 1
    print(
        f"OK: import walls intact ({layers_scanned} layer package(s) scanned, downward-only)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
