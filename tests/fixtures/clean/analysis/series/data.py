"""Fixture: series layer of the clean tree; may import xlrd (sole owner).

Downstream consumers live elsewhere, e.g. analysis/figures/points.csv
(named in this docstring on purpose: docstrings are excluded from the
path-literal rule even though this names a HIGHER layer's path).
"""

import xlrd  # noqa: F401  (legal here: series is the sole xlrd layer)

GROWTH = 0.06
