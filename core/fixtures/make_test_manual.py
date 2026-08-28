"""
Generate a service-manual-shaped PDF for testing the pipeline.

    python -m core.fixtures.make_test_manual

This exists so the extractor can be exercised end to end without shipping a
copyrighted OEM manual in the repo. It is a TEST INPUT, not a demo asset: the
whole point of the pipeline is that it runs on documents nobody wrote for it,
so for a real demo point it at a real manual.

It is deliberately awkward in the ways real manuals are awkward -- running
headers, a parts table, prose wrapped mid-sentence, torque given in both
metric and imperial, warnings mixed into the step text.
"""

from __future__ import annotations

from pathlib import Path

import fitz

DATA = Path(__file__).resolve().parents[2] / "data"
OUT = DATA / "test_manual.pdf"
OUT_TOP_END = DATA / "top_end_reassembly.pdf"

HEAD_FONT, BODY_FONT = "hebo", "helv"
MARGIN, WIDTH, LEADING = 62, 471, 15.4

PAGES: list[tuple[str, list[str]]] = [
    ("SECTION 4 - SHORT BLOCK ASSEMBLY", [
        "$Preparation",
        "Before assembly, wash all components in clean solvent and blow dry. "
        "Inspect the bores and journals for scoring. Replace any component "
        "outside the service limits given in Section 2.",
        "$4.1 Crankcase and crankshaft",
        "1. Mount the crankcase on the engine stand with the cylinder deck facing "
        "up and the sump opening clear of the stand arm.",
        "2. Lubricate the main journals with clean engine oil and lay the "
        "crankshaft into the case, seating it fully in both main bearings.",
        "3. Install the camshaft, aligning the punch mark on the cam gear with "
        "the corresponding mark on the crank gear. WARNING: mis-timed valves "
        "will contact the piston on the first rotation.",
        "4. Rotate the crankshaft two full turns by hand and confirm it turns "
        "freely with no binding before continuing.",
    ]),
    ("SECTION 4 - SHORT BLOCK ASSEMBLY", [
        "$4.2 Connecting rod",
        "5. Position the connecting rod on the crank pin with the oil dipper "
        "facing the camshaft side of the case.",
        "6. Fit the connecting rod cap, matching the alignment marks stamped on "
        "the rod and the cap. The marks must be on the same side.",
        "7. Tighten the connecting rod bolts to 12 N.m in two even stages using "
        "a torque wrench. Do not exceed the specified figure.",
        "$4.3 Cylinder and piston",
        "8. Fit the cylinder barrel to the crankcase deck and draw it down evenly "
        "onto the register.",
        "9. Fit the three compression rings to the piston with the ring gaps "
        "staggered at 120 degrees, using a ring expander.",
        "10. Compress the rings and slide the piston into the bore, then connect "
        "it to the connecting rod with the wrist pin and fit new circlips.",
    ]),
    ("SECTION 4 - SHORT BLOCK ASSEMBLY", [
        "$4.4 Valve train",
        "11. Lap the intake valve into its seat until a continuous grey band is "
        "visible around the full circumference of the face.",
        "12. Lap the exhaust valve into its seat using the same method. The "
        "exhaust valve runs hotter and must seat perfectly.",
        "13. Fit the valve springs and retainers, compressing each spring with a "
        "valve spring compressor to seat the keepers.",
        "$4.5 Cylinder head",
        "14. Place a new cylinder head gasket on the deck, dry. CAUTION: do not "
        "reuse the old gasket and do not apply sealant.",
        "15. Lower the cylinder head onto the gasket without disturbing it, "
        "locating it on the two dowels.",
        "16. Tighten the cylinder head bolts to 24 N.m (17.7 lb-ft) in a crossing "
        "pattern, in two stages. Uneven torque will distort the deck.",
    ]),
    ("SECTION 4 - SHORT BLOCK ASSEMBLY", [
        "$4.6 Final assembly",
        "17. Fit the spark plug and tighten to 18 N.m. Check the electrode gap "
        "before fitting.",
        "18. Fit the flywheel to the tapered crank end, ensuring the key is fully "
        "seated, and tighten the nut to 75 N.m with a torque wrench.",
        "$Torque reference",
        "%Connecting rod bolt          12 N.m",
        "%Cylinder head bolt           24 N.m",
        "%Spark plug                   18 N.m",
        "%Flywheel nut                 75 N.m",
    ]),
]


# A second, narrower job on the same machine. A training library holds several
# procedures per unit, not one; this exercises the pipeline on a document with a
# different scope and its own page numbering.
TOP_END_PAGES: list[tuple[str, list[str]]] = [
    ("SECTION 5 - TOP END REASSEMBLY", [
        "$5.1 Valves",
        "1. Lap the intake valve into its seat until a continuous grey band shows "
        "around the full circumference of the face.",
        "2. Lap the exhaust valve into its seat by the same method.",
        "3. Fit the valve springs and retainers, compressing each spring to seat "
        "the keepers squarely.",
        "$5.2 Cylinder head",
        "4. Fit the cylinder barrel to the crankcase deck if it was disturbed.",
        "5. Place a new cylinder head gasket on the deck. CAUTION: never reuse a "
        "gasket that has been compressed.",
        "6. Lower the cylinder head onto the gasket, locating it on the dowels.",
        "7. Tighten the cylinder head bolts to 24 N.m in a crossing pattern.",
        "8. Fit the spark plug and tighten to 18 N.m.",
    ]),
]


def build(out: Path = OUT, pages=None, first_page: int = 41, section: str = "4") -> Path:
    pages = pages if pages is not None else PAGES
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()

    for page_no, (running_head, blocks) in enumerate(pages, start=first_page):
        page = doc.new_page(width=595, height=842)
        page.insert_text((MARGIN, 46), running_head, fontname=HEAD_FONT, fontsize=8.2, color=(0.42, 0.42, 0.42))
        page.draw_line(fitz.Point(MARGIN, 54), fitz.Point(MARGIN + WIDTH, 54), color=(0.75, 0.75, 0.75), width=0.6)

        y = 86.0
        for block in blocks:
            if block.startswith("$"):
                y += 8
                page.insert_text((MARGIN, y), block[1:], fontname=HEAD_FONT, fontsize=10.4)
                y += LEADING + 3
            elif block.startswith("%"):
                page.insert_text((MARGIN + 8, y), block[1:], fontname="cour", fontsize=9)
                y += LEADING - 2
            else:
                y = _wrap(page, block, y)
                y += 5

        page.insert_text((MARGIN, 800), f"{section}-{page_no - first_page + 1}", fontname=BODY_FONT, fontsize=8, color=(0.45, 0.45, 0.45))
        page.insert_text((MARGIN + WIDTH - 132, 800), "TEST FIXTURE - NOT AN OEM MANUAL",
                         fontname=BODY_FONT, fontsize=6.4, color=(0.62, 0.62, 0.62))

    doc.save(str(out))
    doc.close()
    return out


def _wrap(page: fitz.Page, text: str, y: float) -> float:
    """Greedy wrap at the text column width, preserving the leading number."""
    words, line = text.split(), ""
    for word in words:
        trial = f"{line} {word}".strip()
        if fitz.get_text_length(trial, fontname=BODY_FONT, fontsize=9.6) > WIDTH:
            page.insert_text((MARGIN, y), line, fontname=BODY_FONT, fontsize=9.6)
            y += LEADING
            line = word
        else:
            line = trial
    if line:
        page.insert_text((MARGIN, y), line, fontname=BODY_FONT, fontsize=9.6)
        y += LEADING
    return y


if __name__ == "__main__":
    for path, pages, first, section in (
        (OUT, PAGES, 41, "4"),
        (OUT_TOP_END, TOP_END_PAGES, 61, "5"),
    ):
        p = build(path, pages, first, section)
        print(f"wrote {p}  ({p.stat().st_size / 1024:.0f} KB, {len(pages)} page(s))")
