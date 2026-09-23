# Vendored chart fonts (AD-11)

Static TTF instances of the two chart typefaces. The locked matplotlib
stylesheet (`analysis/figures/style.py`) registers these files and never
points at system fonts, so exports are byte-stable across machines.

| file | family | subfamily | sha256 |
|---|---|---|---|
| `SourceSerif4-Regular.ttf` | Source Serif 4 | Regular | `856ed41f3ec44a9032910b3c17c7dc1cc762da6c6a0f58c791b38c67a70c2aec` |
| `SourceSerif4-Bold.ttf` | Source Serif 4 | Bold | `cfcae605c9db5834dc6e2e5063888ad739333326f0aafe0659866b8586c939b2` |
| `IBMPlexMono-Regular.ttf` | IBM Plex Mono | Regular | `7c6fbddca4b700be918f5f6183d9bd4464fa427fe435f0b480d77fe2bb8c5a43` |

Sources (fetched 2026-09-23; upstream sha256 pinned so a re-pull can
verify byte identity before instancing):

- `SourceSerif4-Regular.ttf` / `SourceSerif4-Bold.ttf`: static instances
  cut from the OFL variable font
  [`SourceSerif4[opsz,wght].ttf` (google/fonts,
  `97b2d4da6e3cb494b5a1e66ae176914d852ccabef49e0c02c0df25f3e39aca0b`)](https://github.com/google/fonts/raw/main/ofl/sourceserif4/SourceSerif4%5Bopsz%2Cwght%5D.ttf)
  with the recipe below.
- `IBMPlexMono-Regular.ttf`: the stock static Regular TTF, committed as
  downloaded — no instancing involved — from
  [ibm/plex](https://github.com/ibm/plex/raw/master/packages/plex-mono/fonts/complete/ttf/IBMPlexMono-Regular.ttf)
  (upstream sha256 `7c6fbddc…8c5a43`, identical to the table above).

Both typefaces are released under the SIL Open Font License 1.1
(Source Serif 4: adobe/source-serif; IBM Plex Mono: ibm/plex). The
variable-font source is not committed; these static instances are the
commit.

## Reproducing the instances byte-for-byte

Pinned environment (Python 3.12, `fonttools` 4.65.0 — a transitive
dependency of matplotlib, already in the lock). Source variable font:
`SourceSerif4[opsz,wght].ttf` from the google/fonts repository (URL and
upstream sha256 in the Sources list above), axes `wght` 200–900 and
`opsz` 8–60.

```python
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

# SourceSerif4-Regular.ttf
font = TTFont("SourceSerif4[opsz,wght].ttf", recalcTimestamp=False)
instancer.instantiateVariableFont(font, {"wght": 400, "opsz": 20}, inplace=True)
font.recalcTimestamp = False  # no head.modified rewrite on save
font.save("SourceSerif4-Regular.ttf")

# SourceSerif4-Bold.ttf
font = TTFont("SourceSerif4[opsz,wght].ttf", recalcTimestamp=False)
instancer.instantiateVariableFont(font, {"wght": 700, "opsz": 20}, inplace=True)
for rec in font["name"].names:  # pin the subfamily naming
    if rec.platformID == 3 and rec.platEncID == 1 and rec.langID == 1033:
        if rec.nameID == 2:
            rec.string = "Bold"
        elif rec.nameID == 4:
            rec.string = "Source Serif 4 Bold"
font.recalcTimestamp = False
font.save("SourceSerif4-Bold.ttf")
```

`recalcTimestamp=False` keeps the `head` table's modified-time stamp from
being rewritten at save time; without it the output is not byte-stable.
Both reproductions above were verified against the committed sha256
column on 2026-09-23. `IBMPlexMono-Regular.ttf` is the stock static
Regular instance from the ibm/plex release (no instancing involved).

## Glyph coverage note

`U+25AE ▮` (the release-stamp block glyph, DESIGN.md `release-stamp`) is
absent from both the IBM Plex Mono and Source Serif 4 instances.
`analysis/figures/style.py` therefore declares the stamp family list as
`["IBM Plex Mono", "DejaVu Sans"]`: the stamp's ASCII runs render in the
vendored mono face and the `▮` falls back to DejaVu Sans (bundled with
matplotlib), so no missing-glyph warning is emitted and no system font
is consulted.
