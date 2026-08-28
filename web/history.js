/**
 * Attempt history.
 *
 * A tool that forgets everything the moment you close the tab is a demo. This
 * keeps the competency records so the library can show what has actually been
 * done against each document.
 *
 * Local storage is the right store for a single-operator install; a deployed
 * version writes these to the training record system the customer already runs.
 */

const KEY = 'crucivex.attempts.v1';
const MAX_PER_DOC = 50;

function readAll() {
  try {
    const raw = localStorage.getItem(KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};   // corrupt or unavailable storage must not break the app
  }
}

function writeAll(all) {
  try {
    localStorage.setItem(KEY, JSON.stringify(all));
  } catch {
    /* quota or private mode; history is a convenience, not a requirement */
  }
}

export function recordAttempt(docId, report) {
  if (!docId) return;
  const all = readAll();
  const list = all[docId] || [];
  list.unshift({
    at: new Date().toISOString(),
    durationSec: Math.round(report.durationSec),
    errors: report.errors,
    actions: report.actions,
  });
  all[docId] = list.slice(0, MAX_PER_DOC);
  writeAll(all);
}

export function attemptsFor(docId) {
  return readAll()[docId] || [];
}

/** Summary for a library card: attempts, best clean time, last run. */
export function summaryFor(docId) {
  const list = attemptsFor(docId);
  if (!list.length) return null;
  const clean = list.filter((a) => a.errors === 0);
  const best = clean.length ? Math.min(...clean.map((a) => a.durationSec)) : null;
  return {
    attempts: list.length,
    bestCleanSec: best,
    lastAt: list[0].at,
    lastErrors: list[0].errors,
  };
}

export function formatDuration(sec) {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function formatWhen(iso) {
  const then = new Date(iso);
  const mins = Math.floor((Date.now() - then.getTime()) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} hr ago`;
  const days = Math.floor(hrs / 24);
  return days === 1 ? 'yesterday' : `${days} days ago`;
}
