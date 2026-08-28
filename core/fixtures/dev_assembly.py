"""
Development fixture: a hand-authored assembly used to exercise the schema,
the validator and the renderer before real extraction output exists.

This is NOT extracted data and is labelled as such everywhere it surfaces.
Every provenance span here is deliberately unverified, so the validator
rejects it on P5. That is the intended result: it demonstrates that the
falsification checks bite. When the real pipeline runs against a real manual,
this file is overwritten and P5 goes green.

    python -m core.fixtures.dev_assembly
"""

from __future__ import annotations

from pathlib import Path

from core.ir.schema import Assembly, Part, Provenance, Step
from core.ir.validate import validate

WEB = Path(__file__).resolve().parents[2] / "web"


def _p(page: int, quote: str) -> Provenance:
    """Fixture provenance: never verified, because there is no source document."""
    return Provenance(page=page, quote=quote, verified=False)


PARTS = [
    ("crankcase", "Crankcase", 1, "GX16-1000"),
    ("crankshaft", "Crankshaft", 1, "GX16-1310"),
    ("camshaft", "Camshaft assembly", 1, "GX16-1420"),
    ("connecting_rod", "Connecting rod", 1, "GX16-1220"),
    ("rod_cap", "Connecting rod cap", 1, "GX16-1221"),
    ("rod_bolt", "Connecting rod bolt", 2, "GX16-1225"),
    ("cylinder_barrel", "Cylinder barrel", 1, "GX16-1110"),
    ("piston", "Piston", 1, "GX16-1210"),
    ("piston_ring", "Piston ring set", 3, "GX16-1211"),
    ("wrist_pin", "Wrist pin", 1, "GX16-1215"),
    ("intake_valve", "Intake valve", 1, "GX16-1451"),
    ("exhaust_valve", "Exhaust valve", 1, "GX16-1452"),
    ("valve_spring", "Valve spring", 2, "GX16-1455"),
    ("head_gasket", "Cylinder head gasket", 1, "GX16-1120"),
    ("cylinder_head", "Cylinder head", 1, "GX16-1100"),
    ("head_bolt", "Cylinder head bolt", 4, "GX16-1105"),
    ("spark_plug", "Spark plug", 1, "BPR6ES"),
    ("flywheel", "Flywheel", 1, "GX16-1510"),
]

# (id, page, text, installs, depends_on, tool, torque, warning)
STEPS = [
    ("s01", 41, "Mount the crankcase on the engine stand with the cylinder deck facing up.",
     ["crankcase"], [], None, None, None),
    ("s02", 42, "Lubricate the main journals with clean engine oil and lay the crankshaft into the case.",
     ["crankshaft"], ["s01"], None, None, None),
    ("s03", 43, "Install the camshaft, aligning the timing mark on the cam gear with the mark on the crank gear.",
     ["camshaft"], ["s02"], None, None,
     "Mis-timed valves will contact the piston on the first rotation."),
    ("s04", 44, "Position the connecting rod on the crank pin with the oil dipper facing the camshaft.",
     ["connecting_rod"], ["s02"], None, None, None),
    ("s05", 44, "Fit the rod cap, matching the alignment marks stamped on the rod and cap.",
     ["rod_cap"], ["s04"], None, None, None),
    ("s06", 44, "Tighten the connecting rod bolts to 12 N.m in two stages.",
     ["rod_bolt"], ["s05"], "torque wrench", 12.0, None),
    ("s07", 45, "Fit the cylinder barrel to the crankcase deck.",
     ["cylinder_barrel"], ["s01"], None, None, None),
    ("s08", 46, "Fit the three compression rings to the piston with the ring gaps staggered at 120 degrees.",
     ["piston", "piston_ring"], [], "ring expander", None, None),
    ("s09", 46, "Compress the rings and slide the piston into the bore, then connect it to the rod with the wrist pin.",
     ["wrist_pin"], ["s06", "s07", "s08"], "ring compressor", None, None),
    ("s10", 48, "Lap and fit the intake valve into its guide.",
     ["intake_valve"], [], None, None, None),
    ("s11", 48, "Lap and fit the exhaust valve into its guide.",
     ["exhaust_valve"], [], None, None, None),
    ("s12", 49, "Fit the valve springs and retainers, compressing each spring to seat the keepers.",
     ["valve_spring"], ["s10", "s11"], "valve spring compressor", None, None),
    ("s13", 50, "Place a new cylinder head gasket on the deck. Do not reuse the old gasket.",
     ["head_gasket"], ["s09"], None, None, None),
    ("s14", 50, "Lower the cylinder head onto the gasket without disturbing it.",
     ["cylinder_head"], ["s12", "s13"], None, None, None),
    ("s15", 50, "Tighten the cylinder head bolts to 24 N.m in a crossing pattern, in two stages.",
     ["head_bolt"], ["s14"], "torque wrench", 24.0,
     "Uneven torque will distort the deck and blow the gasket."),
    ("s16", 51, "Fit the spark plug and tighten to 18 N.m.",
     ["spark_plug"], ["s15"], "plug socket", 18.0, None),
    ("s17", 52, "Fit the flywheel to the tapered crank end and tighten the nut to 75 N.m.",
     ["flywheel"], ["s06"], "torque wrench", 75.0, None),
]


def build() -> Assembly:
    asm = Assembly(
        title="DEV FIXTURE - synthetic, not extracted",
        source_document="no source document",
    )
    asm.parts = [
        Part(id=pid, name=name, qty=qty, part_number=pn, mesh=pid,
             provenance=_p(41, name))
        for pid, name, qty, pn in PARTS
    ]
    asm.steps = [
        Step(id=sid, index=i, text=text, installs=installs, depends_on=deps,
             tool=tool, torque_nm=torque, warning=warning, provenance=_p(page, text))
        for i, (sid, page, text, installs, deps, tool, torque, warning) in enumerate(STEPS)
    ]
    return asm


def main() -> None:
    asm = build()
    report = validate(asm)
    print(report.render())

    asm.save(WEB / "ir.json")
    import json
    (WEB / "validation.json").write_text(
        json.dumps(report.to_dict(), indent=2), encoding="utf-8"
    )
    print(f"  wrote {WEB / 'ir.json'}")
    print(f"  wrote {WEB / 'validation.json'}\n")


if __name__ == "__main__":
    main()
