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
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
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


def test_readme_hero_alt_matches_the_committed_record() -> None:
    """The README's hero image alt is the record's generated
    ``alt_text`` verbatim (D6): a re-pull that re-stamps the record
    must surface here as a stale-alt failure, not drift silently."""
    import json

    readme = REPO_ROOT / "README.md"
    assert readme.is_file(), "the root README.md is missing"
    record_path = (
        REPO_ROOT / "artifacts" / "figures" / "hero_real_growth_v1.figure.json"
    )
    assert record_path.is_file(), "the committed hero record is missing"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    expected_alt = record["alt_text"]["alt_text"]
    # The alt may contain parentheses; anchor on the exact image URL so
    # the match ends at the alt's closing bracket.
    match = re.search(
        r"!\[(.*?)\]\(artifacts/figures/hero_real_growth_v1\.png\)",
        readme.read_text(encoding="utf-8"),
        re.DOTALL,
    )
    assert match is not None, (
        "the README embeds no hero image with URL "
        "artifacts/figures/hero_real_growth_v1.png"
    )
    assert match.group(1) == expected_alt, (
        "the README hero alt has drifted from the committed record's "
        "alt_text.alt_text; re-copy it from the record"
    )
