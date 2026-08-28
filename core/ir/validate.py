"""
Falsification checks over a decoded Assembly.

This module is the answer to "isn't this just a language model making things
up?". A model can emit plausible JSON indefinitely. It cannot make a cyclic
assembly order acyclic, it cannot resolve a reference to a part it never
declared, and it cannot make 400 N.m a sane torque for an M6 bolt.

Each check states a property that a physically buildable procedure must have.
A generated world either satisfies it or is rejected. That is the difference
between a simulation and a hallucination.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.ir.schema import Assembly

# Plausible torque envelope for engine fastener work, in N.m. Anything outside
# this is almost always an OCR error (a decimal point lost, or lb-ft read as
# N.m) rather than a real specification.
#
# The ceiling was 400, which was calibrated on small petrol engines and was
# wrong. A Detroit Diesel Series 53 crankshaft bolt is specified at 290-310
# lb-ft, i.e. up to 420 N.m, so the check was rejecting a correctly extracted
# figure from a real manual. Heavy diesel main and rod bolts reach further
# still; 900 N.m keeps the check useful against lost decimal points without
# calling a genuine specification impossible.
TORQUE_MIN_NM = 0.5
TORQUE_MAX_NM = 900.0

# Below this fraction of verified source spans we do not consider the assembly
# safe to present as document-derived.
PROVENANCE_FLOOR = 0.60

# How many times the printed step numbering may go backwards before we stop
# believing this is a single procedure. Two allows for a manual that restates
# a short sub-sequence or interleaves a numbered note; more than that is a
# document holding several jobs at once.
MAX_NUMBER_RESTARTS = 2


@dataclass
class CheckResult:
    code: str
    name: str
    passed: bool
    detail: str
    fatal: bool = True

    @property
    def status(self) -> str:
        if self.passed:
            return "PASS"
        return "FAIL" if self.fatal else "WARN"


@dataclass
class ValidationReport:
    assembly_title: str
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when no fatal check failed. Warnings do not block."""
        return all(c.passed or not c.fatal for c in self.checks)

    def render(self) -> str:
        """Terminal report. Also what we put on screen during the demo."""
        width = 68
        lines = [
            "",
            f"CRUCIVEX IR VALIDATION - {self.assembly_title}",
            "-" * width,
        ]
        for c in self.checks:
            lines.append(f"  {c.status:<5}  {c.code:<3}  {c.name:<32}  {c.detail}")
        lines.append("-" * width)
        verdict = "ADMISSIBLE" if self.ok else "REJECTED"
        lines.append(f"  {verdict}: {sum(c.passed for c in self.checks)}/{len(self.checks)} checks passed")
        lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "assembly_title": self.assembly_title,
            "ok": self.ok,
            "checks": [
                {
                    "code": c.code,
                    "name": c.name,
                    "status": c.status,
                    "detail": c.detail,
                }
                for c in self.checks
            ],
        }


# ── individual properties ────────────────────────────────────────────────────


def _check_acyclic(asm: Assembly) -> CheckResult:
    """P1 - the dependency graph must topologically sort.

    A cyclic assembly order describes a machine that cannot be built: part A
    must be fitted before B, and B before A. No amount of fluent prose makes
    that physical.
    """
    ids = {s.id for s in asm.steps}
    indegree = {s.id: 0 for s in asm.steps}
    adjacency: dict[str, list[str]] = {s.id: [] for s in asm.steps}

    for s in asm.steps:
        for dep in s.depends_on:
            if dep in ids:
                adjacency[dep].append(s.id)
                indegree[s.id] += 1

    queue = [sid for sid, deg in indegree.items() if deg == 0]
    sorted_count = 0
    while queue:
        node = queue.pop()
        sorted_count += 1
        for nxt in adjacency[node]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)

    if sorted_count == len(asm.steps):
        return CheckResult("P1", "acyclic assembly order", True, f"{sorted_count} steps sorted")
    stuck = len(asm.steps) - sorted_count
    return CheckResult("P1", "acyclic assembly order", False, f"cycle involving {stuck} steps")


def _check_referential_integrity(asm: Assembly) -> CheckResult:
    """P2 - every part and step referenced must have been declared."""
    part_ids = {p.id for p in asm.parts}
    step_ids = {s.id for s in asm.steps}
    dangling: list[str] = []
    refs = 0

    for s in asm.steps:
        for pid in s.installs:
            refs += 1
            if pid not in part_ids:
                dangling.append(f"{s.id}->part:{pid}")
        for dep in s.depends_on:
            refs += 1
            if dep not in step_ids:
                dangling.append(f"{s.id}->step:{dep}")

    if not dangling:
        return CheckResult("P2", "referential integrity", True, f"{refs} references resolved")
    shown = ", ".join(dangling[:3])
    return CheckResult("P2", "referential integrity", False, f"{len(dangling)} dangling: {shown}")


def _check_no_orphan_parts(asm: Assembly) -> CheckResult:
    """P3 - a part nobody installs is either an extraction error or a missing step."""
    installed = {pid for s in asm.steps for pid in s.installs}
    orphans = [p.id for p in asm.parts if p.id not in installed]
    if not orphans:
        return CheckResult("P3", "no orphan parts", True, f"all {len(asm.parts)} parts installed")
    return CheckResult(
        "P3", "no orphan parts", False,
        f"{len(orphans)} never installed: {', '.join(orphans[:3])}",
        fatal=False,
    )


def _check_branches(asm: Assembly) -> CheckResult:
    """P4 - the procedure must have recovered some ordering structure.

    Counts independent branches. Disconnected steps are not a defect: a
    manual is written as one linear list because paper is linear, but valve
    lapping genuinely does not depend on the crankshaft going in. Separate
    branches are the parallelism we recovered, and two technicians can work
    them at once.

    What would be a real failure is recovering *no* structure -- every step
    its own island, meaning we learned nothing the page numbering didn't
    already tell us.
    """
    if len(asm.steps) <= 1:
        return CheckResult("P4", "recovered branches", True, "trivial")

    neighbours: dict[str, set[str]] = {s.id: set() for s in asm.steps}
    for s in asm.steps:
        for dep in s.depends_on:
            if dep in neighbours:
                neighbours[s.id].add(dep)
                neighbours[dep].add(s.id)

    seen: set[str] = set()
    components: list[int] = []
    for step in asm.steps:
        if step.id in seen:
            continue
        size, stack = 0, [step.id]
        seen.add(step.id)
        while stack:
            node = stack.pop()
            size += 1
            for nxt in neighbours[node]:
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        components.append(size)

    components.sort(reverse=True)
    detail = f"{len(components)} independent branches, largest {components[0]} steps"
    # No structure at all: every step isolated.
    if len(components) == len(asm.steps) and len(asm.steps) > 3:
        return CheckResult("P4", "recovered branches", False,
                           "no ordering recovered - every step isolated")
    return CheckResult("P4", "recovered branches", True, detail)


def _check_provenance(asm: Assembly) -> CheckResult:
    """P5 - assertions must trace to verbatim text in the source document."""
    items = asm.provenance_items
    total = len(asm.parts) + len(asm.steps)
    if total == 0:
        return CheckResult("P5", "provenance coverage", False, "empty assembly")

    verified = sum(1 for _, prov in items if prov.verified)
    ratio = verified / total
    detail = f"{verified}/{total} spans verified verbatim ({ratio:.0%})"
    return CheckResult("P5", "provenance coverage", ratio >= PROVENANCE_FLOOR, detail)


def _check_torque_sanity(asm: Assembly) -> CheckResult:
    """P6 - torque figures must be physically plausible for this class of work."""
    specs = [(s.id, s.torque_nm) for s in asm.steps if s.torque_nm is not None]
    if not specs:
        return CheckResult("P6", "torque plausibility", True, "no torque specs to check")

    bad = [f"{sid}={val}" for sid, val in specs if not TORQUE_MIN_NM <= val <= TORQUE_MAX_NM]
    if not bad:
        return CheckResult("P6", "torque plausibility", True, f"{len(specs)} specs in range")
    return CheckResult(
        "P6", "torque plausibility", False,
        f"{len(bad)} implausible: {', '.join(bad[:3])}",
    )


def _check_single_procedure(asm: Assembly) -> CheckResult:
    """P8 - an assembly must be one procedure, not a whole manual.

    This check exists because the suite passed something it should not have. A
    395-page Detroit Diesel manual decoded to a single 2,120-step "assembly"
    and scored 7/7: the graph really was acyclic, every reference really did
    resolve, every span really was verbatim. Each property held, and the
    artifact was still nonsense, because no technician performs 2,120 steps.

    The document contains roughly two hundred separate procedures. The signal
    that gives it away is the printed numbering: a manual restarts at 1 for
    each job, so a genuine single procedure counts up and a concatenation of
    many resets over and over.

    Segmenting the manual into its constituent procedures is the real fix and
    it is not built yet. Until it is, this refuses to call the concatenation
    admissible rather than quietly rendering it.
    """
    numbered = [s.source_number for s in asm.steps if s.source_number is not None]
    if len(numbered) < 2:
        return CheckResult("P8", "single procedure", True, "too few steps to judge")

    restarts = sum(1 for a, b in zip(numbered, numbered[1:]) if b <= a)
    if restarts <= MAX_NUMBER_RESTARTS:
        return CheckResult("P8", "single procedure", True,
                           f"{len(numbered)} steps, {restarts} numbering restart(s)")
    return CheckResult(
        "P8", "single procedure", False,
        f"{restarts} numbering restarts across {len(numbered)} steps "
        f"- this is ~{restarts + 1} procedures concatenated, not one",
    )


def _check_unique_ids(asm: Assembly) -> CheckResult:
    """P7 - duplicate identifiers silently corrupt every downstream lookup."""
    part_ids = [p.id for p in asm.parts]
    step_ids = [s.id for s in asm.steps]
    dup_parts = {i for i in part_ids if part_ids.count(i) > 1}
    dup_steps = {i for i in step_ids if step_ids.count(i) > 1}
    dups = sorted(dup_parts | dup_steps)
    if not dups:
        return CheckResult("P7", "identifier uniqueness", True, f"{len(part_ids) + len(step_ids)} unique ids")
    return CheckResult("P7", "identifier uniqueness", False, f"duplicates: {', '.join(dups[:4])}")


# ── entry point ──────────────────────────────────────────────────────────────


def validate(asm: Assembly) -> ValidationReport:
    """Run every property check against a decoded assembly."""
    return ValidationReport(
        assembly_title=asm.title,
        checks=[
            _check_single_procedure(asm),
            _check_acyclic(asm),
            _check_referential_integrity(asm),
            _check_no_orphan_parts(asm),
            _check_branches(asm),
            _check_provenance(asm),
            _check_torque_sanity(asm),
            _check_unique_ids(asm),
        ],
    )
