/**
 * The provenance drawer.
 *
 * Given a part, shows the span of the source document that put it in the
 * scene: the quote, whether it was located verbatim, and the page image with
 * the matched words boxed.
 *
 * Unverified spans are shown amber rather than hidden. In a regulated shop the
 * seam between what the document said and what the model inferred is the thing
 * being bought.
 */

export function createProvenance(docBase) {
  const panel = document.getElementById('provenance');

  function show(ir, partId) {
    const part = ir.parts.find((p) => p.id === partId);
    if (!part) return;

    const steps = ir.steps.filter((s) => s.installs.includes(partId));
    const spans = [part.provenance, ...steps.map((s) => s.provenance)].filter(Boolean);
    const primary = spans.find((p) => p.verified) || spans[0];

    panel.innerHTML = `
      <div class="prov-head">
        <div>
          <div class="prov-part">${esc(part.name)}</div>
          <div class="prov-sub">${part.part_number ? 'P/N ' + esc(part.part_number) : 'no part number in source'} &middot; qty ${part.qty}</div>
        </div>
        <button id="prov-close" aria-label="Close">&times;</button>
      </div>
      ${primary ? renderSpan(primary) : '<div class="prov-empty">No source span recorded.</div>'}
      <div class="prov-foot">Every object in the scene resolves to a span of the
        source document. Amber means the model went beyond it.</div>`;

    panel.classList.add('open');
    document.body.classList.add('prov-open');
    document.getElementById('prov-close').addEventListener('click', hide);
  }

  function renderSpan(prov) {
    const box = prov.bbox && prov.page_size ? boxStyle(prov.bbox, prov.page_size) : null;
    return `
      <div class="prov-quote ${prov.verified ? 'ok' : 'warn'}">
        <span class="prov-label">${prov.verified ? 'VERBATIM &middot; PAGE ' + prov.page : 'UNVERIFIED INFERENCE'}</span>
        &ldquo;${esc(prov.quote)}&rdquo;
      </div>
      <div class="prov-page">
        <img src="${docBase}pages/page_${prov.page}.png" alt="Source page ${prov.page}"
             onerror="this.parentElement.classList.add('noimg')">
        ${box ? `<div class="prov-hl" style="${box}"></div>` : ''}
      </div>`;
  }

  /** PDF points to percentages of the rendered page image. */
  function boxStyle(bbox, size) {
    const [x0, top, x1, bottom] = bbox;
    const [w, h] = size;
    return `left:${(x0 / w) * 100}%;top:${(top / h) * 100}%;` +
           `width:${((x1 - x0) / w) * 100}%;height:${((bottom - top) / h) * 100}%;`;
  }

  function hide() {
    panel.classList.remove('open');
    document.body.classList.remove('prov-open');
  }

  return { show, hide };
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );
}
