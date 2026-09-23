"""Stamp-byte isolation for the freshness and churn checks.

The stamp bytes legitimately differ between builds (the BUILD-HEAD
leg names the build-input HEAD). Gate 7 and the pipeline's churn rule
therefore never compare stamp bytes: SVG exports are compared with the
``<g id="release-stamp">`` group stripped, PNG exports are compared
pixel-exact outside the stamp keep-out rect, and records are compared
with only the BUILD-HEAD leg of the stamp normalized. The stamp frame
(``release-stamp-frame``) is a constant-geometry, constant-color box
(monospace stamp, fixed line count) and stays in the diff.

The stamp group is NOT flat: matplotlib's SVG backend renders the
multi-line stamp text as one gid group holding, per line, an
``<!-- <line> -->`` comment plus a nested ``<g style=...>`` glyph
block. Stripping it means removing the whole balanced group, comments
included (the comments carry the varying VINTAGE/BUILD-HEAD legs).
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image


def _group_end(text: str, start: int) -> int:
    """Index just past the ``</g>`` closing the ``<g ...>`` opened at ``start``."""
    i = text.index(">", start) + 1
    depth = 1
    while depth:
        nxt_open = text.find("<g", i)
        nxt_close = text.find("</g>", i)
        if nxt_close == -1:
            raise ValueError("unbalanced group: no closing </g> after the stamp group")
        if 0 <= nxt_open < nxt_close:
            depth += 1
            i = nxt_open + 2
        else:
            depth -= 1
            i = nxt_close + len("</g>")
    return i


def strip_stamp_groups(svg_bytes: bytes | str) -> bytes | str:
    """Remove the ``<g id="release-stamp">`` group (the byte-diff norm).

    Removes the whole balanced group -- including the per-line
    ``<!-- ... -->`` comments the SVG backend emits for the stamp text,
    which carry the build-varying VINTAGE and BUILD-HEAD legs.
    Accepts bytes or str and returns the same type.
    Raises ``ValueError`` when the group is absent (the export does not
    carry the baked stamp), when its close is missing, or when a second
    stamp group survives.
    """
    if isinstance(svg_bytes, str):
        text = svg_bytes
        return_text = True
    else:
        text = svg_bytes.decode("utf-8")
        return_text = False
    start = text.find('<g id="release-stamp">')
    if start == -1:
        raise ValueError("stamp group missing from the export")
    end = _group_end(text, start)
    stripped = text[:start] + text[end:]
    if '<g id="release-stamp">' in stripped:
        raise ValueError("more than one release-stamp group in the export")
    return stripped if return_text else stripped.encode("utf-8")


def stamps_match_pre_post(pre_record_bytes: bytes, post_record_bytes: bytes) -> bool:
    """True when two records differ only in the BUILD-HEAD leg.

    A BUILD-HEAD-only difference never triggers a rewrite: the two
    records must otherwise be byte-identical, and both stamps must
    parse with the same VINTAGE and script path.
    """
    import json

    from analysis.figures import _records

    if pre_record_bytes == post_record_bytes:
        return True
    try:
        pre = json.loads(pre_record_bytes)
        post = json.loads(post_record_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False
    if pre.get("stamp") == post.get("stamp"):
        return False  # same stamp but different bytes -> real diff
    pre_stamp = _records.parse_stamp(str(pre.get("stamp", "")))
    post_stamp = _records.parse_stamp(str(post.get("stamp", "")))
    if pre_stamp is None or post_stamp is None:
        return False
    return (
        pre_stamp["vintage"] == post_stamp["vintage"]
        and pre_stamp["script"] == post_stamp["script"]
        and {**pre, "stamp": None} == {**post, "stamp": None}
    )


def png_equal_outside_rect(
    pre_png: bytes, post_png: bytes, rect_px: tuple[int, int, int, int]
) -> bool:
    """Pixel-exact comparison outside the stamp keep-out rect.

    ``rect_px`` is ``(x0, y0, x1, y1)`` in canvas px measured from the
    top-left (the PNG raster order). Any size mismatch is a difference,
    not a match.
    """

    def load(data: bytes) -> np.ndarray:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        return np.asarray(img, dtype=np.uint8)

    a, b = load(pre_png), load(post_png)
    if a.shape != b.shape:
        return False
    x0, y0, x1, y1 = rect_px
    mask = np.ones(a.shape[:2], dtype=bool)
    mask[max(y0, 0) : y1, max(x0, 0) : x1] = False
    return bool(np.array_equal(a[mask], b[mask]))
