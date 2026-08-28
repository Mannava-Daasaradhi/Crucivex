/**
 * The library: what has been ingested, what came out, and what has been done
 * against it.
 *
 * This is the screen the tool opens on. The 3D viewer is one thing you can do
 * with a document, not the whole application.
 */

import { summaryFor, formatDuration, formatWhen } from './history.js';

const MANIFEST = './library/index.json';

const grid = document.getElementById('grid');
const drop = document.getElementById('drop');
const fileInput = document.getElementById('file');
const chooseBtn = document.getElementById('choose');
const msg = document.getElementById('ingest-msg');

async function loadLibrary() {
  let entries = [];
  try {
    const res = await fetch(MANIFEST, { cache: 'no-store' });
    if (res.ok) entries = await res.json();
  } catch {
    /* no manifest yet: an empty library is a valid state, not an error */
  }
  render(entries);
}

function render(entries) {
  if (!entries.length) {
    grid.innerHTML = `<div class="empty">
      No documents yet.<br>Add a service manual above, or run
      <code>python -m core.pipeline &lt;file.pdf&gt;</code>.
    </div>`;
    return;
  }

  // A service manual decodes into hundreds of procedures. Listing them flat
  // buries the three-procedure documents and turns the library into a wall.
  // One collapsed group per manual, standalone documents left as they are.
  const groups = new Map();
  const loose = [];
  for (const e of entries) {
    if (!e.document) { loose.push(e); continue; }
    if (!groups.has(e.document)) groups.set(e.document, []);
    groups.get(e.document).push(e);
  }

  grid.innerHTML =
    loose.map(card).join('') +
    [...groups].map(([doc, items]) => manualGroup(doc, items)).join('');

  for (const head of grid.querySelectorAll('.group-head')) {
    head.addEventListener('click', () => {
      head.parentElement.classList.toggle('open');
    });
  }
}

/** One collapsible block for a manual that split into many procedures. */
function manualGroup(doc, items) {
  const ok = items.filter((e) => e.ok).length;
  const source = items[0]?.source || doc;
  const pages = items[0]?.pages || 0;
  // Strip the shared manual name so each row reads as the procedure it is.
  const shortTitle = (t) => esc(String(t).split(' - ').slice(1).join(' - ') || t);

  return `
    <section class="group">
      <button class="group-head" aria-expanded="false">
        <div>
          <h2>${esc(items[0]?.title.split(' - ')[0] || doc)}</h2>
          <div class="src">${esc(source)} &middot; ${pages} pages &middot;
            ${items.length} procedures decoded</div>
        </div>
        <span class="pill ${ok === items.length ? 'ok' : 'part'}">${ok}/${items.length} VERIFIED</span>
      </button>
      <div class="group-body">
        ${items.map((e) => `
          <a class="row ${e.ok ? '' : 'bad'}" href="./viewer.html?doc=${encodeURIComponent(e.id)}">
            <span class="row-title">${shortTitle(e.title)}</span>
            <span class="row-stats">${e.steps} steps &middot; ${e.parts} parts${
              e.torqueSpecs ? ` &middot; ${e.torqueSpecs} torque` : ''}</span>
            <span class="row-pill">${e.ok ? 'OK' : 'REJECTED'}</span>
          </a>`).join('')}
      </div>
    </section>`;
}

function card(e) {
  const pct = e.totalSpans ? Math.round((e.verifiedSpans / e.totalSpans) * 100) : 0;
  const hist = summaryFor(e.id);

  const history = hist
    ? `${hist.attempts} attempt${hist.attempts > 1 ? 's' : ''} &middot; ` +
      (hist.bestCleanSec != null
        ? `best clean <em>${formatDuration(hist.bestCleanSec)}</em>`
        : `no clean run yet`) +
      ` &middot; last ${formatWhen(hist.lastAt)}`
    : 'Not yet attempted';

  return `
    <a class="card" href="./viewer.html?doc=${encodeURIComponent(e.id)}">
      <div class="card-top">
        <div>
          <h2>${esc(e.title)}</h2>
          <div class="src">${esc(e.source)} &middot; ${e.pages} page${e.pages === 1 ? '' : 's'}</div>
        </div>
        <span class="pill ${e.ok ? 'ok' : 'bad'}">${e.ok ? 'VERIFIED' : 'REJECTED'}</span>
      </div>
      <div class="stats">
        <div><span>PARTS</span><b>${e.parts}</b></div>
        <div><span>STEPS</span><b>${e.steps}</b></div>
        <div><span>TORQUES</span><b>${e.torqueSpecs}</b></div>
        <div><span>SOURCED</span><b>${pct}%</b></div>
      </div>
      <div class="card-foot">${history}</div>
    </a>`;
}

// ── ingestion ────────────────────────────────────────────────────────────────

chooseBtn.addEventListener('click', (e) => { e.preventDefault(); fileInput.click(); });
fileInput.addEventListener('change', () => {
  if (fileInput.files[0]) ingest(fileInput.files[0]);
});

for (const type of ['dragenter', 'dragover']) {
  drop.addEventListener(type, (e) => { e.preventDefault(); drop.classList.add('over'); });
}
for (const type of ['dragleave', 'drop']) {
  drop.addEventListener(type, (e) => { e.preventDefault(); drop.classList.remove('over'); });
}
drop.addEventListener('drop', (e) => {
  const file = e.dataTransfer?.files?.[0];
  if (file) ingest(file);
});

async function ingest(file) {
  if (!/\.pdf$/i.test(file.name)) {
    return say('err', 'That is not a PDF.');
  }
  say('busy', `Extracting ${file.name} — this runs the full pipeline, give it a moment…`);
  chooseBtn.disabled = true;

  try {
    const res = await fetch('/api/ingest', {
      method: 'POST',
      headers: { 'X-Filename': file.name, 'Content-Type': 'application/pdf' },
      body: file,
    });
    const body = await res.json().catch(() => ({}));

    if (!res.ok) {
      // 404 means the static server is running instead of the app server.
      return say('err', res.status === 404
        ? 'Ingestion needs the app server: python -m core.server'
        : body.error || `Ingestion failed (${res.status}).`);
    }
    if (body.warning) say('err', body.warning);
    else say('ok', `${body.title} — ${body.parts} parts, ${body.steps} steps, ${body.verifiedSpans}/${body.totalSpans} spans verified.`);
    await loadLibrary();
  } catch (err) {
    say('err', `Could not reach the server: ${err.message}`);
  } finally {
    chooseBtn.disabled = false;
    fileInput.value = '';
  }
}

function say(kind, text) {
  msg.className = kind;
  msg.textContent = text;
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );
}

loadLibrary();
