/**
 * Perform mode: the assembly as a task, not a tour.
 *
 * Study mode shows the procedure. This hides it and asks you to carry it out.
 * You are given the parts and nothing else; every placement is checked against
 * the dependency graph recovered from the document, and every torque against
 * the figure printed in it.
 *
 * This is the part a video cannot do and a chatbot cannot do. It only exists
 * because the IR carries machine-checkable constraints: an ordering that can be
 * violated and a specification that can be missed. The assessment is not
 * authored by anyone -- it falls out of the document.
 *
 * Everything the operator does is recorded with timings. Where they hesitated
 * and what they reached for first is the signal; it is the reason this medium
 * is worth the trouble.
 */

const TORQUE_TOLERANCE = 0.001;   // spec is exact; this is float slack only

export function createTask(ir) {
  const placed = new Set();
  const trace = [];
  let startedAt = null;
  let lastActionAt = null;
  let pendingTorque = null;       // step awaiting a torque entry

  const stepFor = (partId) => ir.steps.find((s) => s.installs.includes(partId));
  const stepDone = (step) => step.installs.every((p) => placed.has(p));

  function completedStepIds() {
    const done = new Set();
    for (const s of ir.steps) if (stepDone(s)) done.add(s.id);
    return done;
  }

  /** First prerequisite of `step` that has not been satisfied yet. */
  function unmetDependency(step) {
    const done = completedStepIds();
    const id = step.depends_on.find((d) => !done.has(d));
    return id ? ir.steps.find((s) => s.id === id) : null;
  }

  function start(now) {
    startedAt = now;
    lastActionAt = now;
  }

  /**
   * Try to fit a part.
   * @returns {{ok:boolean, reason?:string, blockedBy?:object, step?:object, needsTorque?:boolean}}
   */
  function attempt(partId, now) {
    if (startedAt === null) start(now);
    const hesitation = (now - lastActionAt) / 1000;
    lastActionAt = now;

    const record = (ok, reason) => {
      trace.push({ partId, ok, reason, hesitation, at: (now - startedAt) / 1000 });
    };

    if (pendingTorque) {
      record(false, 'torque-outstanding');
      return { ok: false, reason: `Torque the ${nameOf(pendingTorque.installs[0])} first.` };
    }
    if (placed.has(partId)) {
      record(false, 'already-placed');
      return { ok: false, reason: 'Already fitted.' };
    }

    const step = stepFor(partId);
    if (!step) {
      record(false, 'no-step');
      return { ok: false, reason: 'No step in the document fits this part.' };
    }

    const blocker = unmetDependency(step);
    if (blocker) {
      record(false, 'out-of-order');
      return {
        ok: false,
        blockedBy: blocker,
        reason: `Out of order. This depends on step ${blocker.index + 1}: "${truncate(blocker.text)}"`,
      };
    }

    placed.add(partId);
    record(true, null);

    // A step that specifies a torque is not finished until it is torqued.
    const needsTorque = step.torque_nm != null && stepDone(step);
    if (needsTorque) pendingTorque = step;
    return { ok: true, step, needsTorque };
  }

  /** Check an entered torque against the figure recovered from the document. */
  function submitTorque(value, now) {
    if (!pendingTorque) return { ok: true };
    const spec = pendingTorque.torque_nm;
    const hesitation = (now - lastActionAt) / 1000;
    lastActionAt = now;

    if (Math.abs(value - spec) > TORQUE_TOLERANCE) {
      trace.push({ partId: pendingTorque.installs[0], ok: false, reason: 'wrong-torque', hesitation, at: (now - startedAt) / 1000, entered: value });
      return { ok: false, reason: `${value} N·m is not the specified figure.`, spec };
    }
    trace.push({ partId: pendingTorque.installs[0], ok: true, reason: 'torque-ok', hesitation, at: (now - startedAt) / 1000, entered: value });
    pendingTorque = null;
    return { ok: true };
  }

  const remaining = () => ir.parts.filter((p) => !placed.has(p.id));
  const complete = () => placed.size === ir.parts.length && !pendingTorque;
  const nameOf = (pid) => ir.parts.find((p) => p.id === pid)?.name || pid;

  /** The competency record. This is the artefact the buyer actually wants. */
  function report(now) {
    const errors = trace.filter((t) => !t.ok);
    const byReason = {};
    for (const e of errors) byReason[e.reason] = (byReason[e.reason] || 0) + 1;

    const considered = trace.filter((t) => t.hesitation > 0);
    const longest = considered.reduce(
      (a, b) => (b.hesitation > (a?.hesitation ?? 0) ? b : a), null
    );

    return {
      durationSec: startedAt === null ? 0 : (now - startedAt) / 1000,
      actions: trace.length,
      errors: errors.length,
      byReason,
      longestHesitation: longest
        ? { part: nameOf(longest.partId), seconds: longest.hesitation }
        : null,
      firstErrors: errors.slice(0, 4).map((e) => ({ part: nameOf(e.partId), reason: e.reason })),
      trace,
    };
  }

  return {
    start, attempt, submitTorque, report,
    remaining, complete, nameOf,
    get placed() { return placed; },
    get pendingTorque() { return pendingTorque; },
  };
}

function truncate(s, n = 58) {
  return s.length > n ? s.slice(0, n - 1).trimEnd() + '…' : s;
}
