"""studio -- artifact-level assembly of published study content.

Layer contract: owns assembly of artifact-level content for the
published study (page blocks, manifests it is given; it never
computes). Layer rank ``series < metrics < figures < studio``;
dependencies may point downward only, so this layer may depend on
``analysis.figures``, ``analysis.metrics``, and ``analysis.series``.
"""
