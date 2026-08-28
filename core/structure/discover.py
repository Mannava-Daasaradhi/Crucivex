"""
Learn a document's parts vocabulary from the document.

A hand-written lexicon only works on manuals someone anticipated. Hand the
system a engine it has never seen -- rocker arms, tappets, governor gears, oil
seals -- and every unlisted part is simply invisible, which is the difference
between a fixture and a tool.

Two sources, in order of trust:

  1. The parts table, if the document has one. Item number, part number,
     description, quantity. This is the manufacturer telling you the names.
  2. The prose. Nouns that appear as the object of an assembly verb -- "fit
     the rocker arm", "tighten the flywheel nut" -- are parts by construction,
     because that is what those verbs take as objects.

The seed lexicon is not replaced by this; it contributes synonyms and the
attachment relations that text cannot express. Discovery fills in everything
the seed never heard of.
"""

from __future__ import annotations

import re
from collections import Counter

# Verbs whose direct object, in a procedure, is a component.
# "torque" is deliberately absent: in a manual it is overwhelmingly a noun
# ("uneven torque will distort the deck"), and as a verb it matches headings.
# "tighten" covers the fastener case without the false positives.
ASSEMBLY_VERBS = (
    "fit", "refit", "install", "insert", "place", "position", "mount", "attach",
    "secure", "tighten", "connect", "locate", "lower", "slide", "lay",
    "assemble", "seat", "engage", "replace", "renew", "lubricate", "align",
    "remove", "withdraw", "release", "lift", "detach", "slacken", "lap",
    "rotate", "compress", "draw", "support",
)

# A noun phrase ends at any of these. Without the cut, "mount the crankcase on
# the engine stand" yields the part "crankcase on the".
PHRASE_STOP = {
    "on", "onto", "in", "into", "to", "with", "from", "for", "at", "by", "and",
    "or", "until", "if", "that", "which", "using", "over", "under", "against",
    "so", "then", "when", "while", "before", "after", "as", "is", "are", "was",
    "will", "must", "should", "can", "up", "down", "out", "off", "away",
    "through", "between", "around", "without", "per", "than",
    # Quantifiers mid-phrase: "rotate the crankshaft two full turns" is about
    # the crankshaft, not a component called "crankshaft two full".
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "half", "full", "several", "few", "many", "turn", "turns",
}

# Quantifiers and adjectives that ride in front of a part name.
LEADING_NOISE = (
    "the", "a", "an", "each", "all", "both", "new", "old", "correct", "same",
    "first", "second", "third", "one", "two", "three", "four", "five", "six",
    "original", "used", "spare", "appropriate", "specified", "remaining",
    "any", "some", "this", "that", "its", "their",
)

# Words that are never a component, however they are phrased. Without this the
# miner happily decides that "position", "order" and "the same method" are
# parts of the engine.
NOT_A_PART = {
    "it", "them", "this", "that", "these", "those", "there", "here", "side",
    "end", "face", "order", "stage", "stages", "pattern", "method", "time",
    "times", "way", "hand", "mark", "marks", "figure", "section", "step",
    "steps", "torque", "procedure", "direction", "position", "clearance",
    "surface", "point", "points", "value", "setting", "settings", "amount",
    "sequence", "place", "care", "note", "detail", "details", "diagram",
    "table", "specification", "specifications", "limit", "limits", "tool",
    "tools", "solvent", "oil", "grease", "fuel", "air", "water", "dirt",
    "debris", "damage", "wear", "condition", "service", "assembly", "engine",
    "unit", "component", "components", "part", "parts", "item", "items",
}

# Tool names are objects of "using a ..." not of "fit the ...", but they leak
# in often enough to be worth naming.
TOOL_WORDS = ("wrench", "spanner", "socket", "compressor", "expander", "puller",
              "gauge", "micrometer", "indicator", "driver", "pliers", "hammer")

# Heads that are empty on their own but name a real component when qualified.
QUALIFIED_HEADS = {"assembly", "unit", "set", "kit", "component", "item"}

# The object is captured in a lookahead so the scan position advances only past
# the verb. Consuming the phrase means "compress the rings and slide the piston"
# swallows "slide", and the piston is never discovered at all.
OBJECT_RE = re.compile(
    r"\b(?:" + "|".join(ASSEMBLY_VERBS) + r")\s+"
    r"(?=((?:[a-z][a-z-]*\s+){0,3}[a-z][a-z-]*))",
    re.IGNORECASE,
)

# "12  GX16-1220  CONNECTING ROD  1"  -- item, part number, description, qty.
TABLE_ROW_RE = re.compile(
    r"^\s*(\d{1,3})\s+([A-Z0-9][A-Z0-9\-./]{3,})\s+([A-Za-z][A-Za-z0-9 \-/,.]{3,60}?)\s+(\d{1,2})\s*$"
)

MAX_WORDS = 4
MIN_CHARS = 3


def slugify(phrase: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", phrase.lower()).strip("_")


def singular(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("sses") or word.endswith("shes") or word.endswith("ches"):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def normalise_phrase(phrase: str) -> str | None:
    """Trim a captured noun phrase to a part name, or reject it."""
    words = [w.strip(".,;:()") for w in re.split(r"\s+", phrase.lower().strip())]
    words = [w for w in words if w]

    while words and words[0] in LEADING_NOISE:
        words.pop(0)

    # Cut at the first word that cannot be part of the noun phrase.
    cut = next((i for i, w in enumerate(words) if w in PHRASE_STOP), len(words))
    words = [singular(w) for w in words[:cut]]
    words = [w for w in words if w]

    if not words or len(words) > MAX_WORDS:
        return None

    head = words[-1]
    if len(head) < MIN_CHARS:
        return None
    # "assembly" alone is not a component; "rocker arm assembly" is. Words that
    # are meaningless on their own can still be the head of a real part name.
    if head in NOT_A_PART and not (len(words) > 1 and head in QUALIFIED_HEADS):
        return None
    if head in LEADING_NOISE:        # trailing article: the phrase ran on
        return None
    # Adverbs ("seat it squarely") are not components -- but "assembly" ends in
    # -ly too, and it is one of the commonest heads in a parts list.
    if head.endswith("ly") and head not in QUALIFIED_HEADS:
        return None
    if any(t in head for t in TOOL_WORDS):
        return None
    if all(w in NOT_A_PART for w in words):
        return None
    return " ".join(words)


def parts_from_table(pages: list[dict]) -> dict[str, str]:
    """{normalised name: part number} from any parts-list rows found."""
    found: dict[str, str] = {}
    for page in pages:
        for line in (page.get("text") or "").splitlines():
            m = TABLE_ROW_RE.match(line)
            if not m:
                continue
            name = normalise_phrase(m.group(3))
            if name:
                found.setdefault(name, m.group(2))
    return found


def parts_from_prose(pages: list[dict]) -> Counter:
    """Candidate part names counted by how often they are acted upon."""
    counts: Counter = Counter()
    for page in pages:
        text = page.get("text") or ""
        for m in OBJECT_RE.finditer(text):
            name = normalise_phrase(m.group(1))
            if name:
                counts[name] += 1
    return counts


def _absorb_substrings(names: list[str]) -> dict[str, str]:
    """Map a shorter name onto the longer one that contains it.

    Prose alternates between "the connecting rod" and "the rod" for the same
    component. Left separate they become two parts, and the procedure claims
    to fit both.
    """
    alias: dict[str, str] = {}
    ordered = sorted(names, key=lambda n: len(n.split()), reverse=True)
    for short in names:
        for long in ordered:
            if short == long:
                continue
            # Suffix only. "rod" and "connecting rod" are the same component;
            # "cylinder head" and "cylinder head gasket" are not, and folding
            # them loses a part and invents a dependency.
            if long.endswith(" " + short):
                alias[short] = long
                break
    return alias


def discover(pages: list[dict], seed: dict) -> dict:
    """Build a lexicon for this document.

    Returns the same shape as lexicon.json's "parts", so the rest of the
    extractor does not care whether a name was authored or learned.
    """
    table = parts_from_table(pages)
    prose = parts_from_prose(pages)

    names = set(table) | set(prose)
    alias = _absorb_substrings(sorted(names))
    canonical = {alias.get(n, n) for n in names}

    # Anything the seed already knows keeps its id, its synonyms and its
    # attachment relations; matching is by surface form, not by id.
    seed_by_form: dict[str, str] = {}
    for pid, entry in seed["parts"].items():
        for form in entry["forms"]:
            seed_by_form[form.lower()] = pid

    parts: dict[str, dict] = {}
    for name in sorted(canonical):
        pid = seed_by_form.get(name)
        if pid and pid in seed["parts"]:
            entry = dict(seed["parts"][pid])
            entry["discovered"] = False
        else:
            pid = slugify(name)
            entry = {
                "name": name[:1].upper() + name[1:],
                "forms": [name],
                "discovered": True,
            }
        # Every alias that folded into this name becomes a surface form.
        extra = [s for s, target in alias.items() if target == name]
        entry["forms"] = sorted(set(entry["forms"]) | {name} | set(extra), key=len, reverse=True)
        if name in table:
            entry["part_number"] = table[name]
        parts[pid] = entry

    # Seed parts never mentioned are not in this document and must not appear.
    return {"parts": parts, "tools": seed.get("tools", [])}
