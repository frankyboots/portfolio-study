"""Root-level pytest sentinel.

Having a conftest at the repository root puts the repo root on
``sys.path`` when pytest collects tests, making ``analysis`` (a PEP 420
namespace package; its subpackages like ``series`` are regular packages
with ``__init__.py``) importable from ``tests/`` without installing
anything. No fixtures live here.
"""
