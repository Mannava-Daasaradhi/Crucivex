/**
 * DOM for perform mode. All task logic lives in perform.js; this only renders
 * it and reports operator actions back.
 */

import { createTask } from './perform.js';
import { recordAttempt } from './history.js';

export function createTaskUI(ir, hooks, docId) {
  const el = {
    mode: document.getElementById('mode'),
    title: document.getElementById('aside-title'),
    steps: document.getElementById('steps'),
    task: document.getElementById('task'),
    tray: document.getElementById('tray'),
    msg: document.getElementById('task-msg'),
    timer: document.getElementById('task-timer'),
    errors: document.getElementById('task-errors'),
    left: document.getElementById('task-left'),
    result: document.getElementById('result'),
  };

  let task = null;
  let timerId = null;

  const clock = () => performance.now();

  function enter() {
    task = createTask(ir);
    task.start(clock());
    el.title.textContent = 'TASK — FIT THE ASSEMBLY';
    el.steps.hidden = true;
    el.task.hidden = false;
    el.mode.textContent = 'Exit task';
    el.mode.classList.add('on');
    document.body.classList.add('task-mode');
    el.result.classList.remove('open');
    el.msg.textContent = 'Fit the parts in a valid order. The procedure is hidden.';
    el.msg.className = '';
    renderTray();
    tickTimer();
    timerId = setInterval(tickTimer, 500);
    hooks.onChange(task);
  }

  function exit() {
    clearInterval(timerId);
    timerId = null;
    task = null;
    el.title.textContent = 'PROCEDURE — RECOVERED PARTIAL ORDER';
    el.steps.hidden = false;
    el.task.hidden = true;
    el.mode.textContent = 'Start task';
    el.mode.classList.remove('on');
    document.body.classList.remove('task-mode');
    el.result.classList.remove('open');
    hooks.onExit();
  }

  function tickTimer() {
    if (!task) return;
    const r = task.report(clock());
    el.timer.textContent = fmt(r.durationSec);
    el.errors.textContent = String(r.errors);
    el.left.textContent = String(task.remaining().length);
  }

  function renderTray() {
    el.tray.innerHTML = '';
    // Alphabetical, deliberately not procedure order -- ordering the tray by
    // the answer would hand over the thing we are assessing.
    const parts = [...task.remaining()].sort((a, b) => a.name.localeCompare(b.name));
    for (const p of parts) {
      const b = document.createElement('button');
      b.className = 'tray-item';
      b.textContent = p.name;
      b.addEventListener('click', () => onPick(p.id, b));
      el.tray.appendChild(b);
    }
  }

  function onPick(partId, button) {
    const res = task.attempt(partId, clock());
    if (!res.ok) {
      button.classList.remove('reject');
      void button.offsetWidth;            // restart the animation
      button.classList.add('reject');
      el.msg.className = '';
      el.msg.textContent = res.reason;
      tickTimer();
      return;
    }

    el.msg.className = 'ok';
    el.msg.textContent = res.step.text;
    renderTray();
    hooks.onChange(task, partId);

    if (res.needsTorque) askTorque(res.step);
    else if (task.complete()) finish();
    tickTimer();
  }

  function askTorque(step) {
    el.msg.className = '';
    el.msg.textContent = `${step.text} — enter the torque figure to confirm.`;
    const wrap = document.createElement('div');
    wrap.className = 'torque-entry';
    wrap.innerHTML = `<input type="number" step="0.1" placeholder="N·m" aria-label="Torque in newton metres">
                      <button class="btn">Apply</button>`;
    el.msg.after(wrap);
    const input = wrap.querySelector('input');
    input.focus();

    const submit = () => {
      const val = Number(input.value);
      if (Number.isNaN(val) || input.value === '') return;
      const res = task.submitTorque(val, clock());
      if (!res.ok) {
        el.msg.className = '';
        el.msg.textContent = `${res.reason} Check the figure in the document.`;
        input.select();
        tickTimer();
        return;
      }
      wrap.remove();
      el.msg.className = 'ok';
      el.msg.textContent = `Torqued to ${val} N·m.`;
      tickTimer();
      if (task.complete()) finish();
    };
    wrap.querySelector('button').addEventListener('click', submit);
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
  }

  function finish() {
    clearInterval(timerId);
    const r = task.report(clock());
    const hes = r.longestHesitation;
    recordAttempt(docId, r);

    el.result.innerHTML = `
      <div class="record">
        <h2>COMPETENCY RECORD</h2>
        <div class="record-grid">
          <div><span>ELAPSED</span><b>${fmt(r.durationSec)}</b></div>
          <div><span>ERRORS</span><b>${r.errors}</b></div>
          <div><span>ACTIONS</span><b>${r.actions}</b></div>
        </div>
        <div class="record-note">
          ${r.errors === 0
            ? 'Completed with no ordering or specification violations.'
            : `Violations: ${Object.entries(r.byReason).map(([k, v]) => `${v}&times; ${k.replace(/-/g, ' ')}`).join(', ')}.`}
          ${hes ? ` Longest pause was <em>${hes.seconds.toFixed(1)}s before the ${escapeHtml(hes.part.toLowerCase())}</em>.` : ''}
        </div>
        <div class="record-note" style="margin-top:14px;color:#79828f">
          None of this was authored. The ordering came out of the document, the
          torque figure came out of the document, and what you reached for first
          is the part that exists in no other medium.
        </div>
        <div class="record-foot">
          <button class="btn" id="record-again">Run again</button>
          <button class="btn" id="record-close">Back to procedure</button>
        </div>
      </div>`;
    el.result.classList.add('open');
    document.getElementById('record-again').addEventListener('click', () => { exit(); enter(); });
    document.getElementById('record-close').addEventListener('click', exit);
  }

  el.mode.addEventListener('click', () => (task ? exit() : enter()));

  return { get active() { return !!task; }, get task() { return task; } };
}

function fmt(sec) {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );
}
