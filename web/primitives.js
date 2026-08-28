/**
 * Shared modelling primitives: materials, chamfered castings, fasteners,
 * tubes, springs and cooling fins.
 *
 * Split out of geometry.js so the part builders stay readable. Everything here
 * is generic engineering shape-making; nothing here knows what an engine is.
 */

import * as THREE from './vendor/three.module.js';


// ── materials ────────────────────────────────────────────────────────────────

export const mat = (color, roughness, metalness) =>
  new THREE.MeshStandardMaterial({ color, roughness, metalness });

// Kept deliberately far apart in value. A real teardown reads as dark iron
// against bright machined steel; a single mid-grey for everything makes the
// whole assembly look like one moulded plastic toy.
// Edge lines are what make this read as inspection software rather than a
// failed attempt at photorealism. A chamfered silhouette drawn in crisp line
// work looks deliberate at any polygon count; a smooth-shaded approximation
// of a real casting just looks cheap.
export const EDGE_MATERIAL = new THREE.LineBasicMaterial({
  color: 0xbfe4ff,
  transparent: true,
  opacity: 0.42,
  depthWrite: false,
});

// Above this vertex count the edge pass produces noise rather than structure
// (coil springs, swept tubes), so those parts are left unlined.
export const EDGE_VERTEX_LIMIT = 2600;
export const EDGE_ANGLE = 24;

export const MATERIALS = {
  castIron: mat(0x494e56, 0.78, 0.55),
  aluminium: mat(0x9ba4af, 0.38, 0.9),
  steel: mat(0xc6ccd4, 0.2, 1.0),
  darkSteel: mat(0x353b44, 0.42, 1.0),
  copper: mat(0xb87333, 0.45, 0.9),
  gasket: mat(0xc25a33, 0.88, 0.05),
  ceramic: mat(0xe4dfd4, 0.55, 0.02),
};

// ── small helpers ────────────────────────────────────────────────────────────

/** A hex-headed bolt lying along +Y, seated at the origin. */
export function hexBolt(shankR = 0.16, shankLen = 2.4, headR = 0.34, headH = 0.3) {
  const g = new THREE.Group();
  const shank = new THREE.Mesh(
    new THREE.CylinderGeometry(shankR, shankR, shankLen, 16),
    MATERIALS.steel
  );
  shank.position.y = shankLen / 2;
  const head = new THREE.Mesh(
    new THREE.CylinderGeometry(headR, headR, headH, 6),
    MATERIALS.darkSteel
  );
  head.position.y = shankLen + headH / 2;
  g.add(shank, head);
  return g;
}

/**
 * A box with rounded corners and a chamfered edge, extruded along Y.
 *
 * Perfectly sharp box edges are the single clearest tell of primitive
 * geometry: nothing cast or machined has them, because you cannot get a
 * pattern out of a mould with square corners. A small chamfer catches the key
 * light along every edge and the part starts reading as metal.
 */
export function castBox(w, h, d, radius = 0.22, bevel = 0.08) {
  const r = Math.min(radius, w / 2 - 0.01, d / 2 - 0.01);
  const hw = w / 2, hd = d / 2;
  const s = new THREE.Shape();
  s.moveTo(-hw + r, -hd);
  s.lineTo(hw - r, -hd);
  s.quadraticCurveTo(hw, -hd, hw, -hd + r);
  s.lineTo(hw, hd - r);
  s.quadraticCurveTo(hw, hd, hw - r, hd);
  s.lineTo(-hw + r, hd);
  s.quadraticCurveTo(-hw, hd, -hw, hd - r);
  s.lineTo(-hw, -hd + r);
  s.quadraticCurveTo(-hw, -hd, -hw + r, -hd);

  const geo = new THREE.ExtrudeGeometry(s, {
    depth: Math.max(h - bevel * 2, 0.02),
    bevelEnabled: true,
    bevelSize: bevel,
    bevelThickness: bevel,
    bevelSegments: 2,
    curveSegments: 5,
  });
  geo.rotateX(-Math.PI / 2);          // extrude up the Y axis
  geo.computeBoundingBox();
  const c = new THREE.Vector3();
  geo.boundingBox.getCenter(c);
  geo.translate(-c.x, -c.y, -c.z);    // origin at the centre of the solid
  return geo;
}

/** A raised cylindrical boss, as cast around a bolt hole. */
export function boss(group, x, z, radius, height, y, material) {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius * 1.18, height, 18), material);
  m.position.set(x, y, z);
  group.add(m);
}

/** A tube of finite wall thickness, revolved about Y. */
export function tube(innerR, outerR, height, segments = 56) {
  const h = height / 2;
  const profile = [
    new THREE.Vector2(innerR, -h),
    new THREE.Vector2(outerR, -h),
    new THREE.Vector2(outerR, h),
    new THREE.Vector2(innerR, h),
    new THREE.Vector2(innerR, -h),
  ];
  return new THREE.LatheGeometry(profile, segments);
}

/** A coil spring rising along +Y. */
export function coilSpring(radius, height, turns, wire = 0.07) {
  const pts = [];
  const steps = turns * 20;
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const a = t * turns * Math.PI * 2;
    pts.push(new THREE.Vector3(Math.cos(a) * radius, t * height, Math.sin(a) * radius));
  }
  return new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), steps, wire, 8, false);
}

/** Cooling fins: flat discs stacked along Y. */
export function finStack(group, count, radius, thickness, from, spacing, material) {
  for (let i = 0; i < count; i++) {
    const fin = new THREE.Mesh(
      new THREE.CylinderGeometry(radius, radius, thickness, 48),
      material
    );
    fin.position.y = from + i * spacing;
    group.add(fin);
  }
}

export const rotToX = (geo) => geo.rotateZ(Math.PI / 2);

