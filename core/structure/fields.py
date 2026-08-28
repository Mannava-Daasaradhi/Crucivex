"""Per-step field extraction: torque, tool, hazard clause.

Split out of build_ir so that file stays about the shape of a procedure rather
than the shape of a sentence. Everything here is deterministic and unit-aware;
none of it consults a model.
"""

from __future__ import annotations

import re
from typing import Iterable

# Torque with units. Manuals mix N.m, Nm, N·m and lb-ft freely, so we capture
# the unit and normalise. kgf.m is here because Japanese manuals of the era use
# it almost exclusively -- leaving it out cost us every torque figure in a real
# Isuzu manual. The [lIi1] on the imperial forms is not a typo either: these
# are scans, and OCR routinely reads "lb" as "Ib".
UNIT_ALT = (r"kgf?\s?[.·-]?\s?m(?![a-z])|N\s?[.·-]?\s?m(?![a-z])"
            r"|newton\s?met(?:er|re)s?|[lIi1]bf?[\s.\-]?ft|ft[\s.\-]?[lIi1]bf?")

_NUM = r"\d{1,3}(?:\.\d{1,2})?"

TORQUE_RE = re.compile(
    r"(?P<low>" + _NUM + r")\s*(?:[-–—]\s*(?P<high>" + _NUM + r"))?\s*"
    r"(?P<unit>" + UNIT_ALT + r")",
    re.IGNORECASE,
)

# The tabular form, where the unit is declared as a column header and the value
# follows it, sometimes as a range and sometimes with the conversions bracketed:
#     Rocker Arm Bracket Bolt Torque kg-m(lb.ft/N-m) 1.4 - 2.4 (10 ...
# Scanning for "<number> <unit>" never sees these, because no number precedes
# the unit. This is how the Isuzu manual states every single torque.
TORQUE_TABULAR_RE = re.compile(
    r"(" + UNIT_ALT + r")\s*(?:\([^)]{0,40}\))?\s*"
    r"(" + _NUM + r")\s*(?:[-–—]\s*(" + _NUM + r"))?",
    re.IGNORECASE,
)

LBFT_TO_NM = 1.35582
KGFM_TO_NM = 9.80665

WARNING_RE = re.compile(
    r"\b(warning|caution|note|do not|never|must not)\b[:\s]*(.{10,200}?)(?:\.|$)",
    re.IGNORECASE | re.DOTALL,
)


def _to_nm(value: float, unit: str) -> float:
    u = unit.lower()
    for ch in " -.·":
        u = u.replace(ch, "")
    # Undo the OCR confusion the unit pattern deliberately tolerates. Without
    # this an "Ib-ft" figure falls through unconverted and is emitted as though
    # it were already N.m -- a wrong torque, which is worse than a missing one.
    # It has to apply anywhere in the token, not just at the front, because the
    # reversed spelling "ft-Ib" is just as common in these scans.
    u = u.replace("ib", "lb").replace("1b", "lb")
    if u.startswith(("lbft", "ftlb", "lbfft", "ftlbf")):
        return value * LBFT_TO_NM
    if u.startswith(("kgm", "kgfm")):
        return value * KGFM_TO_NM
    return value


def extract_torque(text: str) -> float | None:
    """Normalised torque in N.m, or None. Other units are converted.

    Where a manual gives a range ("tighten to 290-310 lb-ft") we take the low
    end. A technician who under-torques to the bottom of the band is in spec; a
    validator that reads the top of the band and rejects it is not.
    """
    m = TORQUE_RE.search(text)
    if m:
        return round(_to_nm(float(m.group("low")), m.group("unit")), 1)

    t = TORQUE_TABULAR_RE.search(text)
    if t:
        return round(_to_nm(float(t.group(2)), t.group(1)), 1)
    return None


def extract_tool(text: str, tools: Iterable[str]) -> str | None:
    low = text.lower()
    hits = [t for t in tools if t in low]
    return max(hits, key=len) if hits else None


def action_clause(text: str) -> str:
    """The instruction with any trailing hazard clause removed.

    "Install the camshaft... WARNING: mis-timed valves will contact the piston"
    names the piston as a consequence, not as something being fitted. Scanning
    the whole sentence for parts makes the warning install a piston.
    """
    m = WARNING_RE.search(text)
    return (text[:m.start()] if m else text).strip()


def extract_warning(text: str) -> str | None:
    m = WARNING_RE.search(text)
    if not m:
        return None
    phrase = " ".join(m.group(0).split())
    return phrase if len(phrase) > 16 else None
