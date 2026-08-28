"""Split a manual into the separate procedures it actually contains.

A service manual is not one job. It is a few hundred of them bound together,
and the extractor originally read the whole book as a single assembly: 2,120
steps for a Detroit Diesel Series 53, which no technician performs and which
P8 correctly refuses.

The boundary signal is the numbering the publisher already printed. Paper
procedures restart at 1, so a run of increasing step numbers is one job and a
number that goes backwards is the start of the next. Two weaker signals catch
the cases where numbering alone is ambiguous: a large jump forward usually
means we picked up a different list, and a gap of several pages means whatever
came between was not part of this procedure.

What this does not do is understand the manual's table of contents. A heading
tells you what a procedure is called and this only tells you where one ends.
Naming is best-effort and derived from the first instruction.
"""

from __future__ import annotations

from core.structure.fields import extract_torque

# A step number that jumps forward by more than this is a different list, not
# the next step. Manuals do skip numbers, but not by much.
MAX_NUMBER_GAP = 8

# Procedures run across a page break constantly, so this has to be generous.
# It exists only to catch a run of numbers that happens to keep climbing
# across an unrelated chunk of the book.
MAX_PAGE_GAP = 4

# Below this a "procedure" is a numbered note, a spec table, or a caption. This
# is the single biggest source of noise in a real manual.
MIN_PROCEDURE_STEPS = 4

# ...except when the run states a torque. Setting the bar at four steps threw
# away 12 of the 20 torque specifications in the Isuzu manual, all of them in
# genuine two- and three-step jobs ("Install the thrust plate", "Apply engine
# oil to the bolt and threads"). A torque figure is the strongest available
# evidence that a run describes work on a machine rather than prose about the
# manual, so it buys a run its place at a lower step count.
MIN_STEPS_WITH_TORQUE = 2

# Words that start a numbered *note* rather than an instruction. A manual is
# full of "1. These specifications are based on..." which is prose, not work.
NOTE_OPENERS = (
    "information", "these", "this manual", "the following", "components and",
    "specifications", "refer to", "when ordering", "all dimensions",
    "the illustrations", "note that", "figures in",
)


def _is_boundary(prev: dict, cur: dict) -> bool:
    """True when `cur` starts a new procedure rather than continuing `prev`."""
    a, b = prev.get("number"), cur.get("number")
    if a is None or b is None:
        return False
    if b <= a:
        return True
    if b - a > MAX_NUMBER_GAP:
        return True
    return cur["page"] - prev["page"] > MAX_PAGE_GAP


def split_runs(raw_steps: list[dict]) -> list[list[dict]]:
    """Every maximal run of ascending step numbers, in document order."""
    runs: list[list[dict]] = []
    current: list[dict] = []
    for rs in raw_steps:
        if current and _is_boundary(current[-1], rs):
            runs.append(current)
            current = []
        current.append(rs)
    if current:
        runs.append(current)
    return runs


def _looks_like_notes(run: list[dict]) -> bool:
    """A numbered list of remarks about the manual, not work on a machine."""
    opener = run[0]["text"].strip().lower()
    return opener.startswith(NOTE_OPENERS)


def _substantial(run: list[dict]) -> bool:
    if _looks_like_notes(run):
        return False
    if len(run) >= MIN_PROCEDURE_STEPS:
        return True
    return (len(run) >= MIN_STEPS_WITH_TORQUE
            and any(extract_torque(s["text"]) is not None for s in run))


def procedures(raw_steps: list[dict]) -> list[list[dict]]:
    """Runs that are plausibly real procedures, longest-lived noise removed."""
    return [run for run in split_runs(raw_steps) if _substantial(run)]


def name_for(run: list[dict], index: int) -> str:
    """A human label for a procedure, derived from its first instruction.

    Deliberately not clever. Deriving the real section title needs the heading
    hierarchy, which we do not track yet; inventing a plausible-sounding name
    here would be exactly the kind of unsourced assertion this system exists to
    avoid. The page number is the part a technician can actually check.
    """
    words = run[0]["text"].split()
    lead = " ".join(words[:7]).rstrip(".,;:")
    if len(words) > 7:
        lead += "..."
    return f"p.{run[0]['page']} - {lead}" if lead else f"Procedure {index + 1}"
