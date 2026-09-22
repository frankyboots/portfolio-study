"""figures -- figure data artifacts and their rendering.

Layer contract: owns published figure data artifacts
(manifest-registered JSON/CSV) and matplotlib rendering of the
figures. Layer rank ``series < metrics < figures < studio``;
dependencies may point downward only, so this layer may depend on
``analysis.metrics`` and ``analysis.series``.
"""
