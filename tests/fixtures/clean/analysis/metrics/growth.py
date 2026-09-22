"""Fixture: clean skeleton -- every reference points downward; must pass."""

# Clean, downward-only imports across the layer tree.
from analysis.series import data


def growth() -> float:
    """Placeholder metric built on the series layer."""
    return data.GROWTH
