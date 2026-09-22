"""Fixture: upward import -- metrics importing a higher layer; must FAIL."""

import analysis.studio  # noqa: F401  (rank 3 from rank 1: upward)
