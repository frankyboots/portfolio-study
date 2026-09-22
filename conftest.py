"""Root-level pytest sentinel.

Having a conftest at the repository root puts the repo root on
``sys.path`` when pytest collects tests, making ``analysis.*``
(PEP 420 namespace packages, not installed) importable from ``tests/``.
No fixtures live here.
"""
