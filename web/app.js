/**
 * Crucivex viewer.
 *
 * Compiles an Assembly IR into an interactive scene. This renderer is
 * deliberately dumb about engines: it knows how to walk a procedure DAG, seat
 * parts, and trace any object on screen back to the span of the source
 * document that put it there. Swap the IR and it renders a gearbox.
 *
 * Nothing may appear in this scene that is not in the IR.
 *
 * The visual language is inspection software, not photorealism: crisp edge
 * work, ghosted shells, and leader-line callouts. That reads as precise at any
 * polygon count, where a half-convincing rendering of a real casting does not.
 */

import * as THREE from './vendor/three.module.js';
import {
  container, scene, camera, renderer, controls, assembly,
} from './stage.js';
import { buildPart } from './geometry.js';
import { createCallouts } from './callouts.js';
import { createTaskUI } from './task-ui.js';
import { createProvenance } from './provenance.js';

// Emissive adds directly to outgoing radiance, so against these dark base
// materials even 0.05 turns cast iron into pale cyan. This is a nudge.
const HIGHLIGHT = new THREE.Color(0x00d4ff).multiplyScalar(0.022);
const SELECTED = new THREE.Color(0xf0a500).multiplyScalar(0.032);
const UNLIT = new THREE.Color(0x000000);

const GHOST_OPACITY = 0.11;
const EXPLODE_SCALE = 0.8;
const LABELS_FROM = 0.18;   // explode fraction at which callouts fade in

const state = {
  ir: null,
  report: null,
  stepIndex: 0,
  explode: 0,
  playing: false,
  xray: false,
  parts: new Map(),
  selected: null,
  unmodelled: [],
  desiredTarget: new THREE.Vector3(0, 5, 0),
  desiredDist: 30,
  fitFor: 0,
  azimuthNudge: 0,
};

let taskUI = null;

const fitTmp = new THREE.Vector3();
const boundTmp = new THREE.Vector3();
const proj = new THREE.Vector3();

const callouts = createCallouts(container, camera);

// ── loading the IR ───────────────────────────────────────────────────────────

// Which document this viewer is showing. A URL per document is the difference
// between an app you navigate and a page that renders one hard-coded thing.
const DOC_ID = new URLSearchParams(location.search).get('doc');
export const DOC_BASE = `./library/${DOC_ID}/`;

// A service manual splits into many procedures, each with its own IR, but the
// page images belong to the document and are rendered once. A procedure id is
// the document id with a "-p007" suffix, so strip it to find the page images.
const PARENT_ID = DOC_ID ? DOC_ID.replace(/-p\d{3}$/, '') : DOC_ID;
export const ASSET_BASE = `./library/${PARENT_ID}/`;

async function load() {
  if (!DOC_ID) {
    location.replace('./index.html');
    return;
  }
  const [ir, report] = await Promise.all([
    fetch(DOC_BASE + 'ir.json').then((r) => r.json()),
    fetch(DOC_BASE + 'validation.json').then((r) => r.json()).catch(() => null),
  ]);
  state.ir = ir;
  state.report = report;

  document.getElementById('doc-title').textContent = ir.title;
  document.getElementById('doc-source').textContent = ir.source_document;

  let genericIndex = 0;
  for (const part of ir.parts) {
    const group = buildPart(part.mesh || part.id, part.name);
    if (group.userData.generic) {
      layOutOnBench(group, genericIndex++);
      state.unmodelled.push(part.name);
    }
    group.userData.partId = part.id;
    group.visible = false;
    assembly.add(group);
    state.parts.set(part.id, group);
    callouts.add(part.id, part.name);
  }

  buildStepList();
  buildReportPanel();
  reportUnmodelled();
  setStep(0);

  taskUI = createTaskUI(ir, {
    onChange: syncPerform,
    onExit: () => setStep(state.stepIndex),
  }, DOC_ID);
}

/**
 * In perform mode the scene follows what the operator has actually fitted,
 * not the document order. The step text and the torque readout are cleared --
 * both of them are the answer.
 */
function syncPerform(task, justPlaced) {
  for (const [pid, group] of state.parts) {
    const was = group.visible;
    group.visible = task.placed.has(pid);
    group.userData.active = pid === justPlaced;
    if (group.visible && !was) group.userData.arriving = 1;
  }
  document.getElementById('step-detail').innerHTML = '';
  document.getElementById('torque-hud').innerHTML = '';
  reframe();
}

/**
 * Parts recovered from the document that we have no model for. They are laid
 * out on the bench in front of the assembly rather than dropped into it,
 * because we know they belong to the job but not where they sit.
 */
function layOutOnBench(group, i) {
  const seated = new THREE.Vector3(-7 + (i % 6) * 2.8, -5.2, 9 + Math.floor(i / 6) * 2.6);
  group.userData.seated = seated;
  group.userData.explode = new THREE.Vector3(0, 0, 5);
  group.userData.enter = seated.clone().setY(seated.y + 6);
  group.userData.shell = false;
  group.position.copy(seated);
}

// Naming every unmodelled part is fine for a twenty-part procedure and absurd
// for a seven-hundred-part one -- on a real manual the list covered the whole
// viewport and the scene behind it. Name a few, count the rest.
const UNMODELLED_NAMES_SHOWN = 3;

/** Geometry coverage, said out loud rather than quietly hidden. */
function reportUnmodelled() {
  const el = document.getElementById('unmodelled');
  if (!state.unmodelled.length) return;
  const n = state.unmodelled.length;
  const shown = state.unmodelled.slice(0, UNMODELLED_NAMES_SHOWN).join(', ');
  const rest = n - Math.min(n, UNMODELLED_NAMES_SHOWN);
  el.textContent =
    `${n} of ${state.ir.parts.length} parts shown as generic geometry — no CAD bound: `
    + shown + (rest ? `, and ${rest} more` : '');
  el.hidden = false;
}

// ── procedure ────────────────────────────────────────────────────────────────

function buildStepList() {
  const list = document.getElementById('steps');
  list.innerHTML = '';
  state.ir.steps.forEach((step, i) => {
    const el = document.createElement('button');
    el.className = 'step';
    const verified = step.provenance?.verified;
    el.innerHTML = `
      <span class="step-num">${String(i + 1).padStart(2, '0')}</span>
      <span class="step-body">
        <span class="step-text">${escapeHtml(step.text)}</span>
        <span class="step-meta">
          ${step.torque_nm ? `<span class="tag torque">${step.torque_nm} N&middot;m</span>` : ''}
          ${step.tool ? `<span class="tag">${escapeHtml(step.tool)}</span>` : ''}
          <span class="tag ${verified ? 'ok' : 'warn'}">${verified ? 'p.' + step.provenance.page : 'inferred'}</span>
        </span>
      </span>`;
    el.addEventListener('click', () => setStep(i));
    list.appendChild(el);
  });
}

function setStep(i) {
  // Step navigation is the answer key; it is inert while a task is running.
  if (taskUI?.active) return;
  state.stepIndex = Math.max(0, Math.min(i, state.ir.steps.length - 1));
  const step = state.ir.steps[state.stepIndex];

  const present = new Set();
  for (let s = 0; s <= state.stepIndex; s++) {
    for (const pid of state.ir.steps[s].installs) present.add(pid);
  }

  for (const [pid, group] of state.parts) {
    group.visible = present.has(pid);
    group.userData.active = step.installs.includes(pid);
    group.userData.arriving = group.userData.active ? 1 : 0;
  }

  document.querySelectorAll('.step').forEach((el, idx) => {
    el.classList.toggle('active', idx === state.stepIndex);
    if (idx === state.stepIndex) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  });

  document.getElementById('step-counter').textContent =
    `${state.stepIndex + 1} / ${state.ir.steps.length}`;
  document.getElementById('step-detail').innerHTML = renderStepDetail(step);
  document.getElementById('torque-hud').innerHTML = step.torque_nm
    ? `<span class="torque-value">${step.torque_nm}</span><span class="torque-unit">N&middot;m</span>`
    : '';

  // A small alternating swing so stepping through has motion of its own.
  state.azimuthNudge = (state.stepIndex % 2 ? 1 : -1) * 0.055;
  reframe();
}

function renderStepDetail(step) {
  const prov = step.provenance;
  const badge = prov?.verified
    ? `<span class="tag ok">verified &middot; page ${prov.page}</span>`
    : `<span class="tag warn">not found in source</span>`;
  const parts = step.installs
    .map((id) => state.ir.parts.find((p) => p.id === id)?.name || id)
    .map((n) => `<span class="tag">${escapeHtml(n)}</span>`)
    .join('');
  return `
    <div class="detail-text">${escapeHtml(step.text)}</div>
    <div class="detail-tags">${parts}${badge}</div>
    ${step.warning ? `<div class="detail-warning">${escapeHtml(step.warning)}</div>` : ''}`;
}

/** Fit the camera to whatever is on screen, easing in over a short window. */
function reframe() {
  const box = new THREE.Box3();
  let any = false;
  for (const group of state.parts.values()) {
    if (!group.visible) continue;
    fitTmp.copy(group.userData.seated)
      .addScaledVector(group.userData.explode, state.explode * EXPLODE_SCALE);
    const half = group.userData.halfExtent;
    box.expandByPoint(boundTmp.copy(fitTmp).sub(half));
    box.expandByPoint(boundTmp.copy(fitTmp).add(half));
    any = true;
  }
  if (!any) {
    // Nothing fitted yet. Frame the volume the assembly will occupy so an
    // empty bench reads as empty rather than as a broken viewport.
    state.desiredTarget.set(0, 4, 0);
    state.desiredDist = 34;
    state.fitFor = 1.1;
    return;
  }

  box.getCenter(state.desiredTarget);
  const radius = Math.max(box.getSize(fitTmp).length() * 0.5, 3.5);
  state.desiredDist = radius / Math.tan(THREE.MathUtils.degToRad(camera.fov * 0.5)) * 0.92 + 3;
  state.fitFor = 1.1;
}

// ── provenance ───────────────────────────────────────────────────────────────

const provenance = createProvenance(ASSET_BASE);

function showProvenance(partId) {
  provenance.show(state.ir, partId);
}

function hideProvenance() {
  provenance.hide();
  state.selected = null;
}

// ── picking ──────────────────────────────────────────────────────────────────

const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();

renderer.domElement.addEventListener('pointerdown', (e) => {
  pointer.x = (e.offsetX / container.clientWidth) * 2 - 1;
  pointer.y = -(e.offsetY / container.clientHeight) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);

  const hits = raycaster.intersectObjects(assembly.children, true);
  const hit = hits.find((h) => h.object.visible && !h.object.userData.isEdge);
  if (!hit) return hideProvenance();

  let root = hit.object;
  while (root.parent && !root.userData.partId) root = root.parent;
  if (!root.userData.partId) return;

  state.selected = root.userData.partId;
  showProvenance(state.selected);
});

// ── validation report ────────────────────────────────────────────────────────

function buildReportPanel() {
  const el = document.getElementById('report-body');
  if (!state.report) {
    el.innerHTML = '<div class="prov-empty">No validation report found.</div>';
    return;
  }
  el.innerHTML = state.report.checks
    .map((c) => `<div class="check ${c.status.toLowerCase()}">
        <span class="check-status">${c.status}</span>
        <span class="check-code">${c.code}</span>
        <span class="check-name">${escapeHtml(c.name)}</span>
        <span class="check-detail">${escapeHtml(c.detail)}</span>
      </div>`)
    .join('');
  const verdict = document.getElementById('report-verdict');
  verdict.textContent = state.report.ok ? 'ADMISSIBLE' : 'REJECTED';
  verdict.className = state.report.ok ? 'verdict ok' : 'verdict bad';
}

// ── animation ────────────────────────────────────────────────────────────────

const tmp = new THREE.Vector3();
const clock = new THREE.Clock();
let playTimer = 0;

function tick() {
  requestAnimationFrame(tick);
  const dt = Math.min(clock.getDelta(), 0.05);

  const ghosted = shellsHiding();

  for (const group of state.parts.values()) {
    const { seated, explode, enter } = group.userData;

    tmp.copy(seated).addScaledVector(explode, state.explode * EXPLODE_SCALE);
    if (group.userData.arriving > 0) {
      group.userData.arriving = Math.max(0, group.userData.arriving - dt * 1.6);
      tmp.lerp(enter, ease(group.userData.arriving));
    }
    group.position.lerp(tmp, 1 - Math.pow(0.0015, dt));

    const sel = state.selected === group.userData.partId;
    const tint = sel ? SELECTED : group.userData.active ? HIGHLIGHT : null;
    const ghost = !sel && (
      (state.xray && group.userData.shell) ||
      (ghosted.has(group) && state.explode < 0.3)
    );
    applyMaterial(group, tint, ghost, dt);
  }

  if (state.playing) {
    playTimer += dt;
    if (playTimer > 1.9) {
      playTimer = 0;
      if (state.stepIndex >= state.ir.steps.length - 1) setPlaying(false);
      else setStep(state.stepIndex + 1);
    }
  }

  if (state.fitFor > 0) {
    state.fitFor -= dt;
    const k = 1 - Math.pow(0.05, dt);
    controls.target.lerp(state.desiredTarget, k);

    const dir = fitTmp.copy(camera.position).sub(controls.target);
    if (state.azimuthNudge) {
      const a = state.azimuthNudge * dt * 1.8;
      const cos = Math.cos(a), sin = Math.sin(a);
      const x = dir.x * cos - dir.z * sin;
      dir.z = dir.x * sin + dir.z * cos;
      dir.x = x;
    }
    const dist = THREE.MathUtils.lerp(dir.length(), state.desiredDist, k);
    camera.position.copy(controls.target).addScaledVector(dir.normalize(), dist);
  }

  controls.update();
  renderer.render(scene, camera);
  callouts.update(state.parts, state.explode > LABELS_FROM, state.selected);
}

const ease = (t) => t * t * (3 - 2 * t);

/**
 * Which shells are actually hiding the part this step is working on.
 *
 * Tested geometrically rather than from a hand-written containment table, so
 * it stays correct for any assembly: a shell ghosts only when an active part
 * seats inside its volume. The flywheel bolts to the outside of the crankcase,
 * so finishing the engine leaves it solid instead of see-through.
 */
function shellsHiding() {
  const hiding = new Set();
  const actives = [];
  for (const g of state.parts.values()) {
    if (g.userData.active && !g.userData.shell) actives.push(g);
  }
  if (!actives.length) return hiding;

  for (const shell of state.parts.values()) {
    if (!shell.userData.shell || !shell.visible) continue;
    const c = shell.userData.seated;
    const h = shell.userData.halfExtent;
    for (const a of actives) {
      const p = a.userData.seated;
      if (Math.abs(p.x - c.x) <= h.x &&
          Math.abs(p.y - c.y) <= h.y &&
          Math.abs(p.z - c.z) <= h.z) {
        hiding.add(shell);
        break;
      }
    }
  }
  return hiding;
}

function applyMaterial(group, tint, ghost, dt) {
  const k = 1 - Math.pow(0.02, dt);
  group.traverse((o) => {
    if (!o.isMesh) return;
    if (!o.userData.mat) {
      o.material = o.material.clone();
      o.userData.mat = o.material;
    }
    const m = o.userData.mat;
    m.emissive.lerp(tint ?? UNLIT, k);
    m.emissiveIntensity = 1.0;

    // Fills fade; the edge lines stay. That is the x-ray look.
    const wanted = ghost ? GHOST_OPACITY : 1;
    if (m.opacity !== wanted) {
      m.opacity = THREE.MathUtils.lerp(m.opacity, wanted, k);
      // Snap, or the lerp approaches 1 asymptotically and the material stays
      // flagged transparent forever, costing a sort pass and depth artefacts.
      if (Math.abs(m.opacity - wanted) < 0.01) m.opacity = wanted;
      m.transparent = m.opacity < 0.995;
      m.depthWrite = m.opacity > 0.85;
    }
  });
}

// ── ui wiring ────────────────────────────────────────────────────────────────

function setPlaying(on) {
  state.playing = on;
  const b = document.getElementById('play');
  b.textContent = on ? 'Pause' : 'Play assembly';
  b.classList.toggle('on', on);
}

document.getElementById('prev').addEventListener('click', () => setStep(state.stepIndex - 1));
document.getElementById('next').addEventListener('click', () => setStep(state.stepIndex + 1));
document.getElementById('play').addEventListener('click', () => setPlaying(!state.playing));
document.getElementById('explode').addEventListener('input', (e) => {
  state.explode = Number(e.target.value) / 100;
  reframe();
});
document.getElementById('show-all').addEventListener('click', () => setStep(state.ir.steps.length - 1));
document.getElementById('report-toggle').addEventListener('click', () => {
  document.getElementById('report').classList.toggle('open');
});
document.getElementById('xray').addEventListener('click', (e) => {
  state.xray = !state.xray;
  e.currentTarget.classList.toggle('on', state.xray);
});

window.addEventListener('keydown', (e) => {
  if (e.key === 'ArrowRight') setStep(state.stepIndex + 1);
  if (e.key === 'ArrowLeft') setStep(state.stepIndex - 1);
  if (e.key === ' ') { e.preventDefault(); setPlaying(!state.playing); }
  if (e.key === 'Escape') hideProvenance();
});

function resize() {
  const w = container.clientWidth;
  const h = container.clientHeight;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
  callouts.resize(w, h);
}
window.addEventListener('resize', resize);

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );
}

resize();
tick();
load().catch((err) => {
  document.getElementById('step-detail').innerHTML =
    `<div class="detail-warning">Could not load ir.json &mdash; ${escapeHtml(err.message)}. ` +
    `Serve this directory over HTTP (python -m http.server), not file://.</div>`;
});
