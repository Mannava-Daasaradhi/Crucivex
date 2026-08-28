"""
Crucivex IR — the intermediate representation.

A technical document is a lossy 2D encoding of a 3D, temporal, causal system.
Someone took a machine, flattened it into isometric line art and numbered
prose, and threw away the geometry, the ordering constraints and the failure
modes. This module defines what we decode it back into.

The IR is the product. Renderers are downstream of it: the WebGL viewer, a
headset build, an assessment generator and a printable checklist are all just
compilations of the same Assembly. Nothing in a renderer may invent facts that
are not in here.

Every assertion carries Provenance. An assertion whose quote could not be
found verbatim in the source page is marked unverified rather than dropped --
we would rather show the seam than paper over it.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "0.1.0"


@dataclass
class Provenance:
    """Where an assertion came from in the source document.

    `verified` is set by the extractor only after `quote` has been located
    verbatim in that page's extracted text. An unverified span means the model
    went beyond the document; the UI renders those amber.
    """

    page: int
    quote: str
    verified: bool = False
    char_start: int | None = None
    char_end: int | None = None
    # Union box of the matched words, in PDF points [x0, top, x1, bottom],
    # with the page dimensions needed to place it. This is what lets the
    # viewer draw a highlight on the source page instead of merely naming it.
    bbox: list[float] | None = None
    page_size: list[float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Provenance:
        return cls(
            page=int(d["page"]),
            quote=d.get("quote", ""),
            verified=bool(d.get("verified", False)),
            char_start=d.get("char_start"),
            char_end=d.get("char_end"),
            bbox=d.get("bbox"),
            page_size=d.get("page_size"),
        )


@dataclass
class Part:
    """A physical entity that exists in the assembly."""

    id: str
    name: str
    qty: int = 1
    part_number: str | None = None
    # Key into the procedural geometry library. Absent means we recovered the
    # part from the document but have no geometry bound to it yet -- the UI
    # lists it as unmodelled rather than silently omitting it.
    mesh: str | None = None
    provenance: Provenance | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["provenance"] = self.provenance.to_dict() if self.provenance else None
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Part:
        prov = d.get("provenance")
        return cls(
            id=d["id"],
            name=d["name"],
            qty=int(d.get("qty", 1)),
            part_number=d.get("part_number"),
            mesh=d.get("mesh"),
            provenance=Provenance.from_dict(prov) if prov else None,
        )


@dataclass
class Step:
    """One operation in the procedure.

    `depends_on` makes this a DAG, not a list. Manuals are written as a linear
    sequence because paper is linear, but the real constraint structure is a
    partial order -- rings can go on the piston while the head is being
    prepared. Recovering the partial order from the linear text is a large
    part of what makes this not a transcription tool.
    """

    id: str
    index: int
    text: str
    # The step number as printed in the document, which is not `index`. A
    # manual restarts at 1 for every procedure it contains, so keeping both
    # lets us tell "step 40 of one long job" from "step 1 of the fortieth job".
    source_number: int | None = None
    installs: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    tool: str | None = None
    torque_nm: float | None = None
    warning: str | None = None
    provenance: Provenance | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["provenance"] = self.provenance.to_dict() if self.provenance else None
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Step:
        prov = d.get("provenance")
        torque = d.get("torque_nm")
        return cls(
            id=d["id"],
            index=int(d["index"]),
            text=d.get("text", ""),
            source_number=(int(d["source_number"])
                           if d.get("source_number") is not None else None),
            installs=list(d.get("installs", [])),
            depends_on=list(d.get("depends_on", [])),
            tool=d.get("tool"),
            torque_nm=float(torque) if torque is not None else None,
            warning=d.get("warning"),
            provenance=Provenance.from_dict(prov) if prov else None,
        )


@dataclass
class Assembly:
    """A decoded procedure: the parts, the partial order, and where each came from."""

    title: str
    source_document: str
    parts: list[Part] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    # ── lookups ──────────────────────────────────────────────────────────────

    def part(self, part_id: str) -> Part | None:
        return next((p for p in self.parts if p.id == part_id), None)

    def step(self, step_id: str) -> Step | None:
        return next((s for s in self.steps if s.id == step_id), None)

    @property
    def provenance_items(self) -> list[tuple[str, Provenance]]:
        """Every provenance-bearing assertion, labelled, for coverage stats."""
        items: list[tuple[str, Provenance]] = []
        for p in self.parts:
            if p.provenance:
                items.append((f"part:{p.id}", p.provenance))
        for s in self.steps:
            if s.provenance:
                items.append((f"step:{s.id}", s.provenance))
        return items

    # ── serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "title": self.title,
            "source_document": self.source_document,
            "parts": [p.to_dict() for p in self.parts],
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Assembly:
        return cls(
            title=d.get("title", "Untitled assembly"),
            source_document=d.get("source_document", ""),
            parts=[Part.from_dict(p) for p in d.get("parts", [])],
            steps=[Step.from_dict(s) for s in d.get("steps", [])],
            schema_version=d.get("schema_version", SCHEMA_VERSION),
        )

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | Path) -> Assembly:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
