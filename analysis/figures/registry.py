"""The figure registry: every registered figure builder, by figure ID.

The pipeline's ``figures`` stage and gate 7 iterate this map. Adding a
figure means adding one module under ``analysis/figures/`` with a
``build_figure(root) -> int`` entry point and one entry here — the
registry is the closed set of published figures.
"""

from __future__ import annotations

import importlib
from pathlib import Path

#: figure ID -> builder module (the module exposes build_figure).
FIGURE_BUILDERS: dict[str, str] = {
    "rebalance_growth_v1": "analysis.figures.rebalance_growth",
    "hero_real_growth_v1": "analysis.figures.hero_real_growth",
}

BUILDERS_BY_ID = FIGURE_BUILDERS


def build_all(root: Path) -> int:
    """Build every registered figure under ``root``; 0 only when all pass."""
    failures: list[str] = []
    for name in sorted(FIGURE_BUILDERS):
        module = importlib.import_module(FIGURE_BUILDERS[name])
        rc = module.build_figure(root)
        if rc != 0:
            failures.append(f"{name} (exit {rc})")
    if failures:
        print(f"figures: failed: {', '.join(failures)}", flush=True)
        return 1
    print(f"figures: built {len(FIGURE_BUILDERS)} figure(s)")
    return 0
