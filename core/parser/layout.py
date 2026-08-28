"""Page layout reconstruction: positioned words -> reading-order text.

Real service manuals are set in two columns. That single fact breaks the
obvious implementation, which is to sort words by vertical position and join
everything on the same line. On a two-column page that interleaves the columns
line by line, so you get text like:

    On 8V engines, tighten the | ""-14 crankshaft bolt necessary. hold a block

which is the left column and the right column zipped together. The damage is
not cosmetic. A step ends up holding half of an unrelated instruction, and a
torque figure from one column gets attached to a step in the other.

So we look for the gutter first: a vertical band of whitespace no word crosses.
If there is one, each column is read top to bottom in turn. If there is not, we
fall back to the naive single-column reading, which is correct for the many
pages that really are one column.
"""

from __future__ import annotations

# Fraction of page height treated as running header / footer. Repetition only
# identifies furniture once you have several pages; position identifies it on
# the first one, which is what a single-page procedure needs.
HEADER_BAND = 0.075
FOOTER_BAND = 0.925

LINE_TOLERANCE = 3.0

# A gutter narrower than this is just inter-word spacing, not a column break.
MIN_GUTTER_FRAC = 0.02
# Gutters live near the middle. A gap in the outer thirds is a wide margin or
# an indented block, and splitting on it would invent columns that aren't there.
GUTTER_SEARCH = (0.30, 0.70)
# Both sides must carry real text, otherwise this is a hanging indent.
MIN_SIDE_SHARE = 0.20
# Words wider than this span the gutter by design (full-width headings, rules).
# They are excluded from gap detection and emitted ahead of the columns.
SPANNING_FRAC = 0.40


def body_words(words: list[dict], height: float) -> list[dict]:
    """Words inside the body band, i.e. with running heads and folios dropped."""
    if not words or height <= 0:
        return []
    return [
        w for w in words
        if w["top"] > HEADER_BAND * height and w["bottom"] < FOOTER_BAND * height
    ]


def find_gutter(words: list[dict], width: float) -> float | None:
    """Centre x of the column gutter, or None if the page is single column."""
    if width <= 0 or len(words) < 20:
        return None

    narrow = [w for w in words if (w["x1"] - w["x0"]) < SPANNING_FRAC * width]
    if len(narrow) < 20:
        return None

    spans: list[list[float]] = []
    for x0, x1 in sorted((w["x0"], w["x1"]) for w in narrow):
        if spans and x0 <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], x1)
        else:
            spans.append([x0, x1])

    best = None
    for i in range(len(spans) - 1):
        gap_start, gap_end = spans[i][1], spans[i + 1][0]
        gap = gap_end - gap_start
        centre = (gap_start + gap_end) / 2
        if gap < MIN_GUTTER_FRAC * width:
            continue
        if not (GUTTER_SEARCH[0] * width < centre < GUTTER_SEARCH[1] * width):
            continue
        if best is None or gap > best[0]:
            best = (gap, centre)

    if best is None:
        return None

    centre = best[1]
    left = sum(1 for w in narrow if w["x1"] <= centre)
    if min(left, len(narrow) - left) < MIN_SIDE_SHARE * len(narrow):
        return None
    return centre


def _lines(words: list[dict]) -> list[str]:
    """Group words into lines by vertical position, each read left to right."""
    rows: dict[int, list[dict]] = {}
    for w in words:
        rows.setdefault(int(w["top"] / LINE_TOLERANCE), []).append(w)
    return [
        " ".join(w["text"] for w in sorted(rows[k], key=lambda w: w["x0"]))
        for k in sorted(rows)
    ]


def page_text(words: list[dict], width: float, height: float) -> str | None:
    """Reading-order text for a page, or None if it has no positioned words.

    None means the caller should keep whatever the OCR or vision tier produced;
    those tiers return a string with no coordinates for us to work from.
    """
    body = body_words(words, height)
    if not body:
        return None

    gutter = find_gutter(body, width)
    if gutter is None:
        return "\n".join(_lines(body))

    spanning, left, right = [], [], []
    for w in body:
        if (w["x1"] - w["x0"]) >= SPANNING_FRAC * width or (w["x0"] < gutter < w["x1"]):
            spanning.append(w)
        elif w["x1"] <= gutter:
            left.append(w)
        else:
            right.append(w)

    out: list[str] = []
    for group in (spanning, left, right):
        if group:
            out.extend(_lines(group))
    return "\n".join(out)
