"""README_NO_CLAIMS (spec D6): the root README carries no vintage claims.

Gate 6 scans docs/, web/, manual/ — the root README is deliberately
out of that surface — so this test applies gate 6's claim patterns to
README.md directly, under the stricter D6 rule: the README never
states a sha256 pin, a K value, or a "last row YYYY.MM" claim (those
live in ``data/DATA.md`` by reference; a restatement would drift on
every re-pull).
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE6_PY = REPO_ROOT / "scripts" / "check_crossdoc_consistency.py"


def _load_gate6_patterns() -> dict:
    """Gate 6's claim patterns, reused verbatim (D8: no re-implemented
    second copy of the regexes that could drift)."""
    spec = importlib.util.spec_from_file_location("crossdoc_under_test", GATE6_PY)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return {
        "hex64": module.HEX64_RE,
        "k": module.K_RE,
        "last_row": module.LAST_ROW_RE,
    }


def test_readme_states_no_vintage_pin() -> None:
    readme = REPO_ROOT / "README.md"
    assert readme.is_file(), "the root README.md is missing"
    patterns = _load_gate6_patterns()
    violations: list[str] = []
    for lineno, line in enumerate(readme.read_text(encoding="utf-8").splitlines(), 1):
        for hex_candidate in patterns["hex64"].findall(line):
            violations.append(
                f"README.md:{lineno}: 64-hex sha256 claim {hex_candidate[:12]}... "
                "(vintage pins live in data/DATA.md by reference)"
            )
        for k_candidate in patterns["k"].findall(line):
            violations.append(
                f"README.md:{lineno}: K claim {k_candidate!r} "
                "(vintage pins live in data/DATA.md by reference)"
            )
        # The gate-6 last-row claim: a YYYY.MM on a line saying "last row".
        if re.search(r"last row", line, re.IGNORECASE):
            for years, months in patterns["last_row"].findall(line):
                if 1 <= int(months) <= 12:
                    violations.append(
                        f"README.md:{lineno}: last row {years}.{months} claim "
                        "(vintage pins live in data/DATA.md by reference)"
                    )
    assert not violations, "\n".join(violations)
