"""Fixture: xlrd outside series -- xlrd import in metrics; must FAIL."""

import xlrd  # noqa: F401  (xlrd belongs only in analysis.series)
