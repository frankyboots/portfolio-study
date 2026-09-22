"""Fixture: figures layer of the clean tree (deeper chain, downward only)."""

from analysis.metrics import growth
from analysis.series import data  # noqa: F401  (skipping straight down is fine too)

# Lower-layer and same-layer path literals: neither may be flagged.
LOWER_CSV = "analysis/series/data.csv"  # noqa: F841  (rank 0 from rank 2: downward)
SAME_LAYER_CSV = "analysis/figures/points.csv"  # noqa: F841  (same layer: not a wall)


def points() -> float:
    """Placeholder figure data artifact built on the metrics layer."""
    return growth.growth()
