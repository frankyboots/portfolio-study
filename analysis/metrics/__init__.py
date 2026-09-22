"""metrics -- portfolio metrics computed over the canonical series.

Layer contract: owns growth/drawdown/other metric computation
built on ``analysis.series``. Layer rank ``series < metrics < figures
< studio``; dependencies may point downward only, so this layer may
depend on ``analysis.series`` and on nothing else in the layer tree.
"""
