"""
Document text -> Assembly IR.

The spine of this extractor is deterministic: regex over numbered steps, a
domain lexicon over part names, unit-aware torque parsing, and dependency
inference from part mentions. No language model is required to produce an IR,
and none is required to reproduce one.

That matters for two reasons. It means the output is stable -- the same
document yields the same world every time -- and it means provenance is
verified by construction rather than asserted. Every span we emit is a slice
of the page text at known character offsets, which we then re-locate to prove
it. A model can claim a citation. This can be checked.

An optional enrichment pass can layer a model on top for the genuinely
ambiguous cases. It is off by default and it can only ever *add* fields that
are then marked unverified.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from core.ir.schema import Assembly, Part, Provenance, Step
from core.structure.discover import discover
from core.structure.fields import (
    action_clause, extract_tool, extract_torque, extract_warning,
)
from core.structure.segment import name_for, procedures

LEXICON_PATH = Path(__file__).with_name("lexicon.json")

# Start of a numbered instruction. Requiring a capital or bracket after the
# number keeps us off parts-table rows and figure callouts, which are also
# numbered but are not procedure steps.
#
# We match only the *start* and take the body up to the next step. Matching a
# whole line instead truncates every instruction that wraps, which is most of
# them -- and silently drops any torque figure that landed on line two.
#
# Manuals number steps in whatever way the publisher settled on decades ago:
#   1.   1)   (1)   1 -   Step 1.   STEP 1:
# Handling only the first of those means a document is silently read as having
# no procedure at all, which is the single most damaging failure mode here.
#
# The separator must be followed by whitespace, which is what keeps section
# headings like "9.1 Rocker gear" from being read as step 9.
STEP_START_RE = re.compile(
    r"(?mi)^[ \t]*(?:step[ \t]*)?\(?(\d{1,3})\)?[.):–-][ \t]+(?=[A-Z(\"'])"
)

# A numbered section heading, e.g. "4.3 Cylinder and piston". These sit
# between steps and must not be swallowed into the preceding step's body.
#
# The trailing class must be a capital, not any non-space: a torque table puts
# its value range on its own line ("2.7 - 3.3 (20.5 - 23.7)"), which is shaped
# exactly like a decimal section number. Reading it as a heading cut the step
# there and severed every torque in the manual from the label naming it.
HEADING_RE = re.compile(r"(?m)^[ \t]*\d+\.\d+[ \t]+[A-Z]")

# An unnumbered heading, e.g. "Torque reference" or "Special tools". Short,
# capitalised, no terminal punctuation. Wrapped continuation lines are long
# and usually start lower case, so they are not caught by this.
BARE_HEADING_RE = re.compile(r"(?m)^[ \t]*([A-Z][^\n.:;,!?]{0,44})[ \t]*$")
BARE_HEADING_MAX_WORDS = 6

MIN_STEP_CHARS = 15

# ── lexicon ──────────────────────────────────────────────────────────────────


def load_lexicon(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or LEXICON_PATH).read_text(encoding="utf-8"))


def _ordered_forms(lex: dict[str, Any]) -> list[tuple[str, str]]:
    """(surface form, part id), longest first so specific names win.

    Without this ordering 'connecting rod cap' matches the part 'connecting
    rod' and the cap is never seen.
    """
    forms: list[tuple[str, str]] = []
    for pid, entry in lex["parts"].items():
        for f in entry["forms"]:
            forms.append((f.lower(), pid))
    forms.sort(key=lambda t: len(t[0]), reverse=True)
    return forms


# ── field extraction ─────────────────────────────────────────────────────────


def normalise(text: str) -> str:
    """Collapse all whitespace. Line breaks in a PDF are typography, not content."""
    return " ".join(text.split())


def strip_page_furniture(pages: list[dict], threshold: float = 0.4) -> list[dict]:
    """Remove running headers, footers and page numbers.

    Every manual repeats a section title at the top of each page and a folio
    at the bottom. Left in, that furniture gets swallowed into whichever step
    happens to sit next to it, and the instruction text ends with the name of
    the chapter.

    We find it structurally rather than by pattern: a line whose digit-stripped
    form recurs across a large fraction of pages is furniture, because real
    instruction text does not repeat verbatim page after page.
    """
    if len(pages) < 3:
        return pages

    def skeleton(line: str) -> str:
        return re.sub(r"\d+", "#", " ".join(line.split())).lower()

    seen_on: dict[str, set[int]] = {}
    for page in pages:
        for line in (page.get("text") or "").splitlines():
            key = skeleton(line)
            if len(key) < 4:
                continue
            seen_on.setdefault(key, set()).add(page["page"])

    cutoff = max(2, int(len(pages) * threshold))
    furniture = {k for k, seen in seen_on.items() if len(seen) >= cutoff}
    if not furniture:
        return pages

    cleaned = []
    for page in pages:
        kept = [
            line for line in (page.get("text") or "").splitlines()
            if skeleton(line) not in furniture
        ]
        cleaned.append({**page, "text": "\n".join(kept)})
    return cleaned


def split_steps(raw: str) -> list[tuple[int, str]]:
    """(step number, body) for each numbered instruction on a page.

    A step's body runs from its number to the next step's number, minus any
    section heading that intervenes.
    """
    starts = list(STEP_START_RE.finditer(raw))
    out: list[tuple[int, str]] = []
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(raw)
        body = raw[m.end():end]
        body = body[:_first_heading(body)]
        out.append((int(m.group(1)), body))
    return out


def _first_heading(body: str) -> int:
    """Offset of the first heading inside a step body, or len(body)."""
    cut = len(body)
    numbered = HEADING_RE.search(body)
    if numbered:
        cut = numbered.start()
    for m in BARE_HEADING_RE.finditer(body):
        if m.start() >= cut:
            break
        if len(m.group(1).split()) <= BARE_HEADING_MAX_WORDS:
            cut = m.start()
            break
    return cut


# A part can be named as a landmark rather than as a thing being worked on:
# "facing the camshaft side of the case" tells you which way round the rod
# goes, it does not mean the camshaft must be fitted first. Treating these as
# dependencies produces a procedure that rejects correct work.
LOCATIVE_AFTER = ("side", "end", "face", "flange", "boss", "bore", "seat")
LOCATIVE_BEFORE = (
    "facing the", "toward the", "towards the", "away from the",
    "opposite the", "adjacent to the", "next to the", "against the",
    "clear of the", "in line with the",
)


def _match_span(low: str, idx: int, form: str) -> int | None:
    """End offset of a form matched at `idx`, or None if it is not a real match.

    Accepts a trailing plural 's'. Manuals name parts in the singular in the
    parts list and the plural in the prose -- "tighten the connecting rod
    bolts" -- so exact-token matching silently loses every fastener.
    """
    if idx > 0 and low[idx - 1].isalnum():
        return None
    end = idx + len(form)
    if end < len(low) and low[end] == "s":
        nxt = low[end + 1] if end + 1 < len(low) else " "
        if not nxt.isalnum():
            return end + 1
    after = low[end] if end < len(low) else " "
    return end if not after.isalnum() else None


def _is_locative(low: str, idx: int, end: int) -> bool:
    after = low[end:].lstrip()
    if after.split(" ", 1)[0].rstrip(",.") in LOCATIVE_AFTER:
        return True
    before = low[:idx].rstrip()
    return any(before.endswith(cue) for cue in LOCATIVE_BEFORE)


def mentioned_parts(text: str, forms: list[tuple[str, str]]) -> list[str]:
    """Part ids mentioned in a step, in order of first appearance.

    Matched regions are blanked out as we go so that a longer form consumes
    the text a shorter form would otherwise also match.
    """
    low = text.lower()
    found: list[tuple[int, str]] = []
    for form, pid in forms:
        idx = low.find(form)
        while idx != -1:
            end = _match_span(low, idx, form)
            if end is not None:
                if not _is_locative(low, idx, end):
                    found.append((idx, pid))
                # Blank it either way, so a shorter form does not re-match the
                # words this one already accounted for.
                low = low[:idx] + "\0" * (end - idx) + low[end:]
                break
            idx = low.find(form, idx + 1)
    seen: set[str] = set()
    ordered = []
    for _, pid in sorted(found):
        if pid not in seen:
            seen.add(pid)
            ordered.append(pid)
    return ordered


# ── provenance ───────────────────────────────────────────────────────────────


def locate_bbox(words: list[dict], quote: str) -> list[float] | None:
    """Union bbox of the word run matching `quote`, in PDF points.

    pdfplumber gives us a box per word. We slide over the word list looking
    for the token sequence of the quote and union the boxes it covers, which
    is what lets the viewer draw a highlight on the source page rather than
    just naming it.
    """
    target = [w for w in re.split(r"\s+", quote.lower()) if w]
    if not target or not words:
        return None
    norm = [re.sub(r"[^\w.\-]", "", w["text"].lower()) for w in words]
    target = [re.sub(r"[^\w.\-]", "", t) for t in target]

    n = len(target)
    for i in range(len(norm) - n + 1):
        if norm[i:i + n] == target:
            run = words[i:i + n]
            return [
                min(w["x0"] for w in run),
                min(w["top"] for w in run),
                max(w["x1"] for w in run),
                max(w["bottom"] for w in run),
            ]
    return None


def make_provenance(
    page_no: int,
    page_text: str,
    quote: str,
    words: list[dict] | None,
    page_size: tuple[float, float] | None,
) -> Provenance:
    """Build a span and prove it by re-locating the quote in the page text."""
    idx = page_text.find(quote)
    prov = Provenance(
        page=page_no,
        quote=quote if len(quote) <= 240 else quote[:237] + "...",
        verified=idx != -1,
        char_start=idx if idx != -1 else None,
        char_end=idx + len(quote) if idx != -1 else None,
    )
    if prov.verified and words:
        bbox = locate_bbox(words, quote)
        if bbox:
            prov.bbox = bbox
            prov.page_size = list(page_size) if page_size else None
    return prov


# ── assembly construction ────────────────────────────────────────────────────


def build_assembly(
    pages: list[dict],
    title: str,
    source_document: str,
    page_words: dict[int, list[dict]] | None = None,
    page_sizes: dict[int, tuple[float, float]] | None = None,
    lexicon: dict[str, Any] | None = None,
) -> Assembly:
    """Decode a procedure out of extracted page text.

    `pages` is the output of core.parser.extract_text: one dict per page with
    at least `page` and `text`.
    """
    ctx = _document_context(pages, lexicon, page_words, page_sizes)
    return _assemble(ctx["raw_steps"], ctx, title, source_document)


def build_assemblies(
    pages: list[dict],
    title: str,
    source_document: str,
    page_words: dict[int, list[dict]] | None = None,
    page_sizes: dict[int, tuple[float, float]] | None = None,
    lexicon: dict[str, Any] | None = None,
) -> list[Assembly]:
    """Decode every procedure the document contains, in order.

    A single-procedure document yields a one-element list identical to what
    build_assembly returns. A real service manual yields one Assembly per job,
    which is the only shape that can pass P8 -- and the only shape a technician
    can actually be handed.

    Vocabulary is discovered once across the whole document, because part names
    are a property of the machine rather than of any one procedure. Everything
    else -- which parts a procedure installs, what depends on what -- is scoped
    to the procedure, since a manual reinstalls the same part in twenty jobs.
    """
    ctx = _document_context(pages, lexicon, page_words, page_sizes)
    runs = procedures(ctx["raw_steps"])
    if len(runs) <= 1:
        return [_assemble(ctx["raw_steps"], ctx, title, source_document)]
    return [
        _assemble(run, ctx, f"{title} - {name_for(run, i)}", source_document)
        for i, run in enumerate(runs)
    ]


def _document_context(
    pages: list[dict],
    lexicon: dict[str, Any] | None,
    page_words: dict[int, list[dict]] | None,
    page_sizes: dict[int, tuple[float, float]] | None,
) -> dict[str, Any]:
    """Everything derived once per document rather than once per procedure."""
    pages = strip_page_furniture(pages)

    # The vocabulary comes from the document. The checked-in lexicon is only a
    # seed: it supplies synonyms and the attachment relations prose cannot
    # state, and contributes nothing for a part this manual never mentions.
    lex = lexicon or discover(pages, load_lexicon())

    raw_steps: list[dict] = []
    for page in pages:
        raw = page.get("text") or ""
        # Provenance is checked against whitespace-normalised page text so a
        # quote that wrapped across lines in the PDF still matches verbatim.
        norm_page = normalise(raw)
        for number, body in split_steps(raw):
            sentence = normalise(body)
            if len(sentence) < MIN_STEP_CHARS:
                continue
            raw_steps.append({
                "page": page["page"],
                "number": number,
                "text": sentence,
                "page_text": norm_page,
            })

    # Parts are declared by the steps that touch them. A part named nowhere in
    # the procedure is not part of this procedure.
    for rs in raw_steps:
        rs["action"] = action_clause(rs["text"])

    return {
        "lex": lex,
        "forms": _ordered_forms(lex),
        "tools": [t.lower() for t in lex["tools"]],
        "page_words": page_words or {},
        "page_sizes": page_sizes or {},
        "raw_steps": raw_steps,
    }


def _assemble(
    raw_steps: list[dict],
    ctx: dict[str, Any],
    title: str,
    source_document: str,
) -> Assembly:
    """Build one Assembly from one run of steps, using document vocabulary."""
    lex, forms, tools = ctx["lex"], ctx["forms"], ctx["tools"]
    page_words, page_sizes = ctx["page_words"], ctx["page_sizes"]

    first_mention: dict[str, dict] = {}
    for rs in raw_steps:
        for pid in mentioned_parts(rs["action"], forms):
            first_mention.setdefault(pid, rs)

    asm = Assembly(title=title, source_document=source_document)

    for pid, rs in first_mention.items():
        entry = lex["parts"][pid]
        asm.parts.append(Part(
            id=pid,
            name=entry["name"],
            qty=1,
            part_number=entry.get("part_number"),
            # The viewer resolves this to real geometry when it recognises the
            # id, and to a generic shape otherwise. A part we cannot model is
            # still a part of the procedure.
            mesh=pid,
            provenance=make_provenance(
                rs["page"], rs["page_text"], rs["text"],
                page_words.get(rs["page"]), page_sizes.get(rs["page"]),
            ),
        ))

    installed_by: dict[str, str] = {}   # part id -> step id that installs it
    for i, rs in enumerate(raw_steps):
        sid = f"s{i + 1:02d}"
        parts = mentioned_parts(rs["action"], forms)

        # A step installs the parts it mentions that nothing has installed yet;
        # parts it mentions that are already in place are dependencies, not
        # installations. This is what separates "fit the piston" from "check
        # the piston moves freely".
        installs = [p for p in parts if p not in installed_by]
        depends = {installed_by[p] for p in parts if p in installed_by}

        # Assembly semantics the prose never states. "Tighten the connecting
        # rod bolts" names only the bolts -- the longest-form match consumes
        # the words "connecting rod", so the step looks independent of the rod
        # it is clamping. The attaches_to relation restores that edge.
        for pid in installs:
            for host in lex["parts"][pid].get("attaches_to", []):
                if host in installed_by:
                    depends.add(installed_by[host])
        depends.discard(sid)

        asm.steps.append(Step(
            id=sid,
            index=i,
            text=rs["text"],
            source_number=rs.get("number"),
            installs=installs,
            depends_on=sorted(depends),
            tool=extract_tool(rs["text"], tools),
            torque_nm=extract_torque(rs["text"]),
            warning=extract_warning(rs["text"]),
            provenance=make_provenance(
                rs["page"], rs["page_text"], rs["text"],
                page_words.get(rs["page"]), page_sizes.get(rs["page"]),
            ),
        ))
        for p in installs:
            installed_by[p] = sid

    return asm
