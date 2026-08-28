/**
 * Leader-line callouts.
 *
 * Projects parts to screen space and lays their labels out in two margin
 * columns with straight leaders back to the part, the way a technical
 * illustration does it. Labels are pooled and only transformed per frame --
 * rebuilding the DOM every frame at 60fps is not survivable.
 */

import * as THREE from './vendor/three.module.js';

const MIN_GAP = 26;      // px between stacked labels in a column
const EDGE_INSET = 18;   // px from the viewport edge to the label
// Clears the torque readout, which is positioned inside the viewport and so
// sits lower down the page than its own top offset suggests.
const TOP_PAD = 96;

const proj = new THREE.Vector3();

export function createCallouts(container, camera) {
  const layer = document.getElementById('labels');
  const svg = document.getElementById('leaders');
  const labels = new Map();

  /** Create the pooled DOM for one part. Called once, at load. */
  function add(partId, text) {
    const el = document.createElement('div');
    el.className = 'callout';
    el.innerHTML = `<span class="callout-text"></span>`;
    el.firstChild.textContent = text;
    el.style.opacity = '0';
    layer.appendChild(el);

    const line = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
    line.setAttribute('class', 'leader');
    svg.appendChild(line);

    labels.set(partId, { el, line });
  }

  function hide(lab) {
    lab.el.style.opacity = '0';
    lab.line.style.opacity = '0';
  }

  /**
   * @param parts    Map of part id -> THREE.Object3D
   * @param showAll  label everything visible, not just the active part
   * @param selected part id currently selected, or null
   */
  function update(parts, showAll, selected) {
    const w = container.clientWidth;
    const h = container.clientHeight;
    const items = [];

    for (const [pid, group] of parts) {
      const lab = labels.get(pid);
      if (!lab) continue;

      const active = group.userData.active || pid === selected;
      if (!group.visible || !(showAll || active)) { hide(lab); continue; }

      proj.copy(group.position).project(camera);
      if (proj.z > 1) { hide(lab); continue; }   // behind the camera

      items.push({
        lab, active,
        ax: (proj.x * 0.5 + 0.5) * w,
        ay: (-proj.y * 0.5 + 0.5) * h,
      });
    }

    const byY = (a, b) => a.ay - b.ay;
    place(items.filter((i) => i.ax < w * 0.5).sort(byY), EDGE_INSET, h, 'left');
    place(items.filter((i) => i.ax >= w * 0.5).sort(byY), w - EDGE_INSET, h, 'right');
  }

  function place(items, edgeX, h, side) {
    let cursor = TOP_PAD;
    for (const it of items) {
      // Keep the stack monotonic so leaders never cross each other.
      const y = Math.max(cursor, Math.min(it.ay, h - TOP_PAD));
      cursor = y + MIN_GAP;

      const { el, line } = it.lab;
      el.style.opacity = it.active ? '1' : '0.72';
      el.classList.toggle('active', it.active);
      el.style.transform = side === 'left'
        ? `translate(${edgeX}px, ${y}px) translateY(-50%)`
        : `translate(${edgeX}px, ${y}px) translate(-100%, -50%)`;

      // Leader runs from the label's inner edge, out to a shoulder, then to
      // the part. The shoulder is what keeps it reading as draughting.
      const inner = side === 'left' ? edgeX + el.offsetWidth + 4 : edgeX - el.offsetWidth - 4;
      const shoulder = side === 'left' ? inner + 14 : inner - 14;
      line.setAttribute('points', `${inner},${y} ${shoulder},${y} ${it.ax},${it.ay}`);
      line.style.opacity = it.active ? '0.85' : '0.4';
    }
  }

  function resize(w, h) {
    svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
    svg.setAttribute('width', w);
    svg.setAttribute('height', h);
  }

  return { add, update, resize };
}
