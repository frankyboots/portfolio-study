"""series -- canonical dataset I/O and 60/40 series construction.

Layer contract: owns the Shiller dataset (this is the ONLY layer
allowed to import ``xlrd``) and the canonical monthly 60/40 total-return
series built from it. Layer rank ``series < metrics < figures <
studio``; dependencies may point downward only, so this layer depends
on no other layer package. Nothing above may import it in reverse.
"""
