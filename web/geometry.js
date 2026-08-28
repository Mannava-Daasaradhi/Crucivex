/**
 * Procedural geometry for a single-cylinder four-stroke engine, plus the
 * generic-shape fallback for parts recovered from a document we cannot model.
 *
 * Every part here is generated at load time. Nothing is fetched, nothing is
 * licensed, nothing can fail to download on stage.
 *
 * This is deliberately the *replaceable* layer. In production a part binds to
 * the customer's own CAD out of their PLM -- they already own it and already
 * pay to maintain it. The IR does not care which it gets: it addresses parts
 * by id, and geometry resolves that id to something with a shape.
 */

import * as THREE from './vendor/three.module.js';
import {
  MATERIALS, EDGE_MATERIAL, EDGE_VERTEX_LIMIT, EDGE_ANGLE,
  mat, hexBolt, tube, coilSpring, finStack, castBox, boss, rotToX,
} from './primitives.js';

export { MATERIALS, EDGE_MATERIAL };

// ── part builders ────────────────────────────────────────────────────────────

function buildCrankcase() {
  const g = new THREE.Group();

  const body = new THREE.Mesh(castBox(9, 6.4, 7, 0.5, 0.12), MATERIALS.castIron);
  g.add(body);

  // Machined deck the barrel bolts down onto, proud of the casting.
  const deck = new THREE.Mesh(castBox(7.2, 0.7, 6.4, 0.35, 0.07), MATERIALS.aluminium);
  deck.position.y = 3.5;
  g.add(deck);

  // Sump flange, wider than the case and thinner.
  const sump = new THREE.Mesh(castBox(8.6, 0.55, 6.8, 0.4, 0.07), MATERIALS.castIron);
  sump.position.y = -3.45;
  g.add(sump);

  // Main bearing housings on the crank axis, with a machined face.
  for (const x of [-4.4, 4.4]) {
    const housing = new THREE.Mesh(rotToX(new THREE.CylinderGeometry(1.45, 1.6, 0.7, 28)), MATERIALS.castIron);
    housing.position.set(x, 0, 0);
    const face = new THREE.Mesh(rotToX(new THREE.CylinderGeometry(1.15, 1.15, 0.12, 28)), MATERIALS.aluminium);
    face.position.set(x + Math.sign(x) * 0.38, 0, 0);
    g.add(housing, face);
  }

  // Cast-in stiffening ribs down the flanks. Real cases are never slab-sided.
  for (const z of [-3.52, 3.52]) {
    for (const x of [-2.6, 0, 2.6]) {
      const rib = new THREE.Mesh(castBox(0.55, 4.6, 0.3, 0.12, 0.05), MATERIALS.castIron);
      rib.position.set(x, -0.3, z);
      g.add(rib);
    }
  }

  // Bolt bosses around the deck.
  for (const x of [-2.9, 2.9]) {
    for (const z of [-2.6, 2.6]) boss(g, x, z, 0.46, 0.5, 3.6, MATERIALS.castIron);
  }
  return g;
}

function buildCrankshaft() {
  const g = new THREE.Group();

  for (const x of [-3.6, 3.6]) {
    const journal = new THREE.Mesh(rotToX(new THREE.CylinderGeometry(0.72, 0.72, 2.4, 24)), MATERIALS.steel);
    journal.position.x = x;
    g.add(journal);
  }
  // Counterweights, mass opposite the pin.
  for (const x of [-1.5, 1.5]) {
    const cw = new THREE.Mesh(rotToX(new THREE.CylinderGeometry(2.1, 2.1, 0.85, 32)), MATERIALS.steel);
    cw.position.set(x, -0.35, 0);
    g.add(cw);
  }
  // Crank pin, offset by the throw.
  const pin = new THREE.Mesh(rotToX(new THREE.CylinderGeometry(0.62, 0.62, 2.6, 24)), MATERIALS.steel);
  pin.position.set(0, 1.35, 0);
  g.add(pin);

  // Output snout.
  const snout = new THREE.Mesh(rotToX(new THREE.CylinderGeometry(0.55, 0.55, 2.2, 20)), MATERIALS.steel);
  snout.position.x = 5.6;
  g.add(snout);
  return g;
}

function buildConnectingRod() {
  const g = new THREE.Group();

  const bigEnd = new THREE.Mesh(new THREE.TorusGeometry(1.05, 0.32, 12, 40), MATERIALS.steel);
  bigEnd.rotation.y = Math.PI / 2;
  g.add(bigEnd);

  const beam = new THREE.Mesh(new THREE.BoxGeometry(0.62, 3.4, 0.95), MATERIALS.steel);
  beam.position.y = 2.0;
  g.add(beam);

  const smallEnd = new THREE.Mesh(new THREE.TorusGeometry(0.52, 0.26, 12, 32), MATERIALS.steel);
  smallEnd.rotation.y = Math.PI / 2;
  smallEnd.position.y = 3.85;
  g.add(smallEnd);
  return g;
}

function buildRodCap() {
  const g = new THREE.Group();
  const cap = new THREE.Mesh(
    new THREE.TorusGeometry(1.05, 0.32, 12, 40, Math.PI),
    MATERIALS.steel
  );
  cap.rotation.y = Math.PI / 2;
  cap.rotation.x = Math.PI;
  g.add(cap);
  // Bolt lands either side of the bore.
  for (const z of [-1.25, 1.25]) {
    const ear = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.5, 0.55), MATERIALS.steel);
    ear.position.set(0, -0.1, z);
    g.add(ear);
  }
  return g;
}

function buildRodBolts() {
  const g = new THREE.Group();
  for (const z of [-1.25, 1.25]) {
    const bolt = hexBolt(0.13, 1.0, 0.26, 0.24);
    bolt.rotation.x = Math.PI; // threads point up into the rod
    bolt.position.set(0, -0.35, z);
    g.add(bolt);
  }
  return g;
}

function buildPiston() {
  const g = new THREE.Group();
  const r = 1.78;
  // Crown, ring land, skirt.
  const profile = [
    new THREE.Vector2(0, 1.15),
    new THREE.Vector2(r, 1.15),
    new THREE.Vector2(r, 0.42),
    new THREE.Vector2(r - 0.12, 0.36),
    new THREE.Vector2(r - 0.12, -0.28),
    new THREE.Vector2(r, -0.34),
    new THREE.Vector2(r, -1.7),
    new THREE.Vector2(r - 0.22, -1.7),
    new THREE.Vector2(r - 0.22, 0.9),
    new THREE.Vector2(0, 0.9),
  ];
  const body = new THREE.Mesh(new THREE.LatheGeometry(profile, 56), MATERIALS.aluminium);
  g.add(body);

  // Pin bosses.
  const boss = new THREE.Mesh(rotToX(new THREE.CylinderGeometry(0.5, 0.5, 2.9, 20)), MATERIALS.aluminium);
  boss.position.y = -0.75;
  g.add(boss);
  return g;
}

function buildPistonRings() {
  const g = new THREE.Group();
  [0.34, 0.04, -0.3].forEach((y) => {
    const ring = new THREE.Mesh(new THREE.TorusGeometry(1.72, 0.085, 8, 56), MATERIALS.darkSteel);
    ring.rotation.x = Math.PI / 2;
    ring.position.y = y;
    g.add(ring);
  });
  return g;
}

function buildWristPin() {
  const pin = new THREE.Mesh(rotToX(new THREE.CylinderGeometry(0.34, 0.34, 3.1, 20)), MATERIALS.steel);
  const g = new THREE.Group();
  g.add(pin);
  return g;
}

function buildCylinderBarrel() {
  const g = new THREE.Group();
  const barrel = new THREE.Mesh(tube(1.8, 2.35, 7.2), MATERIALS.castIron);
  g.add(barrel);
  finStack(g, 11, 2.72, 0.12, -2.9, 0.56, MATERIALS.castIron);
  // Base flange onto the crankcase deck.
  const flange = new THREE.Mesh(new THREE.CylinderGeometry(3.0, 3.0, 0.5, 40), MATERIALS.castIron);
  flange.position.y = -3.4;
  g.add(flange);
  return g;
}

function buildHeadGasket() {
  const g = new THREE.Group();
  const gasket = new THREE.Mesh(tube(1.82, 3.0, 0.14), MATERIALS.gasket);
  g.add(gasket);
  return g;
}

function buildCylinderHead() {
  const g = new THREE.Group();
  const body = new THREE.Mesh(castBox(6.2, 1.9, 6.2, 0.55, 0.1), MATERIALS.aluminium);
  g.add(body);
  // Rocker cover, so the valve gear reads as enclosed rather than floating.
  const cover = new THREE.Mesh(castBox(4.6, 1.7, 5.0, 0.6, 0.09), MATERIALS.aluminium);
  cover.position.y = 1.75;
  g.add(cover);
  finStack(g, 5, 2.66, 0.12, 0.62, 0.34, MATERIALS.aluminium);

  // Head bolt bosses, and a machined gasket face on the underside.
  for (const x of [-2.4, 2.4]) {
    for (const z of [-2.4, 2.4]) boss(g, x, z, 0.44, 0.4, -0.75, MATERIALS.aluminium);
  }
  const gasketFace = new THREE.Mesh(castBox(5.9, 0.12, 5.9, 0.5, 0.04), MATERIALS.steel);
  gasketFace.position.y = -0.98;
  g.add(gasketFace);

  // Valve seats visible from below.
  for (const z of [-1.0, 1.0]) {
    const seat = new THREE.Mesh(new THREE.CylinderGeometry(0.78, 0.78, 0.2, 28), MATERIALS.darkSteel);
    seat.position.set(0, -0.95, z);
    g.add(seat);
  }
  return g;
}

function buildHeadBolts() {
  const g = new THREE.Group();
  for (const x of [-2.4, 2.4]) {
    for (const z of [-2.4, 2.4]) {
      const bolt = hexBolt(0.19, 3.0, 0.4, 0.34);
      bolt.position.set(x, -1.2, z);
      g.add(bolt);
    }
  }
  return g;
}

function valve() {
  const g = new THREE.Group();
  const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.15, 2.4, 16), MATERIALS.steel);
  stem.position.y = 1.2;
  g.add(stem);
  const head = new THREE.Mesh(new THREE.CylinderGeometry(0.76, 0.6, 0.3, 28), MATERIALS.darkSteel);
  g.add(head);
  return g;
}

const buildIntakeValve = () => valve();
const buildExhaustValve = () => valve();

function buildValveSprings() {
  const g = new THREE.Group();
  for (const z of [-1.0, 1.0]) {
    const spring = new THREE.Mesh(coilSpring(0.4, 1.9, 7), MATERIALS.darkSteel);
    spring.position.set(0, 0, z);
    g.add(spring);
  }
  return g;
}

function buildCamshaft() {
  const g = new THREE.Group();
  const shaft = new THREE.Mesh(rotToX(new THREE.CylinderGeometry(0.42, 0.42, 6.4, 20)), MATERIALS.steel);
  g.add(shaft);
  // Two lobes: base circle with an offset nose.
  for (const x of [-1.3, 1.3]) {
    const base = new THREE.Mesh(rotToX(new THREE.CylinderGeometry(0.72, 0.72, 0.7, 28)), MATERIALS.steel);
    base.position.x = x;
    const nose = new THREE.Mesh(rotToX(new THREE.CylinderGeometry(0.44, 0.44, 0.7, 20)), MATERIALS.steel);
    nose.position.set(x, 0.5, 0);
    g.add(base, nose);
  }
  const gear = new THREE.Mesh(rotToX(new THREE.CylinderGeometry(1.5, 1.5, 0.45, 40)), MATERIALS.steel);
  gear.position.x = 3.0;
  g.add(gear);
  return g;
}

function buildFlywheel() {
  const g = new THREE.Group();
  const disc = new THREE.Mesh(rotToX(new THREE.CylinderGeometry(3.5, 3.5, 0.7, 48)), MATERIALS.castIron);
  g.add(disc);
  const hub = new THREE.Mesh(rotToX(new THREE.CylinderGeometry(1.1, 1.1, 1.4, 24)), MATERIALS.steel);
  g.add(hub);
  // Cooling vanes.
  for (let i = 0; i < 8; i++) {
    const a = (i / 8) * Math.PI * 2;
    const vane = new THREE.Mesh(new THREE.BoxGeometry(0.35, 1.9, 0.5), MATERIALS.castIron);
    vane.position.set(-0.5, Math.cos(a) * 2.3, Math.sin(a) * 2.3);
    vane.rotation.x = -a;
    g.add(vane);
  }
  return g;
}

function buildSparkPlug() {
  const g = new THREE.Group();
  const ceramic = new THREE.Mesh(new THREE.CylinderGeometry(0.34, 0.42, 1.9, 20), MATERIALS.ceramic);
  ceramic.position.y = 1.4;
  g.add(ceramic);
  const hex = new THREE.Mesh(new THREE.CylinderGeometry(0.46, 0.46, 0.4, 6), MATERIALS.darkSteel);
  hex.position.y = 0.3;
  g.add(hex);
  const thread = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.3, 0.9, 16), MATERIALS.steel);
  thread.position.y = -0.4;
  g.add(thread);
  return g;
}

// ── the library ──────────────────────────────────────────────────────────────
//
// `pos`     seated position in the finished assembly
// `explode` unit-ish direction the part travels in the exploded view
// `enter`   offset the part animates in from when its step fires

// Explode vectors separate along distinct axes on purpose. Pushing everything
// straight up leaves the whole bottom end -- crank, rod, piston, cam, the
// parts worth looking at -- buried inside an opaque crankcase.
//
//   down      crankshaft
//   -Z        connecting rod, cap, bolts
//   +Z        camshaft
//   +X        piston, rings, wrist pin
//   -X        flywheel
//   up        barrel, gasket, head, bolts, valve gear
export const PART_LIBRARY = {
  // `shell` marks a part that encloses others. Shells ghost out when the step
  // is working on something inside them, so the piston is visible in the bore
  // instead of hidden behind an opaque casting.
  crankcase:       { build: buildCrankcase,      pos: [0, 0, 0],       explode: [0, 0, 0],      enter: [0, 0, 0], shell: true },
  crankshaft:      { build: buildCrankshaft,     pos: [0, -0.6, 0],    explode: [0, -8, 0],     enter: [0, -9, 0] },
  flywheel:        { build: buildFlywheel,       pos: [-5.4, -0.6, 0], explode: [-8, -3, 0],    enter: [-11, -0.6, 0] },
  camshaft:        { build: buildCamshaft,       pos: [0, 1.1, 2.6],   explode: [0, -3, 9],     enter: [0, 1.1, 11] },
  connecting_rod:  { build: buildConnectingRod,  pos: [0, 0.75, 0],    explode: [0, -1.5, -9],  enter: [0, 9, -3] },
  rod_cap:         { build: buildRodCap,         pos: [0, 0.75, 0],    explode: [0, -4.5, -9],  enter: [0, -6, -3] },
  rod_bolt:        { build: buildRodBolts,       pos: [0, 0.75, 0],    explode: [0, -7, -9],    enter: [0, -8, -3] },
  piston:          { build: buildPiston,         pos: [0, 5.35, 0],    explode: [9, 1, 0],      enter: [11, 6, 0] },
  piston_ring:     { build: buildPistonRings,    pos: [0, 5.35, 0],    explode: [9, 4.5, 0],    enter: [11, 9, 0] },
  wrist_pin:       { build: buildWristPin,       pos: [0, 4.6, 0],     explode: [9, -2, 0],     enter: [12, 4.6, 0] },
  cylinder_barrel: { build: buildCylinderBarrel, pos: [0, 6.6, 0],     explode: [0, 3.5, 0],    enter: [0, 15, 0], shell: true },
  head_gasket:     { build: buildHeadGasket,     pos: [0, 10.3, 0],    explode: [0, 6.5, 0],    enter: [0, 17, 0] },
  cylinder_head:   { build: buildCylinderHead,   pos: [0, 11.35, 0],   explode: [0, 9.5, 0],    enter: [0, 19, 0], shell: true },
  head_bolt:       { build: buildHeadBolts,      pos: [0, 11.35, 0],   explode: [0, 15, 0],     enter: [0, 22, 0] },
  intake_valve:    { build: buildIntakeValve,    pos: [0, 10.5, -1.0], explode: [-7, 11, -3],   enter: [0, 20, -1.0] },
  exhaust_valve:   { build: buildExhaustValve,   pos: [0, 10.5, 1.0],  explode: [-7, 11, 3],    enter: [0, 20, 1.0] },
  valve_spring:    { build: buildValveSprings,   pos: [0, 11.2, 0],    explode: [7, 11, 0],     enter: [0, 21, 0] },
  spark_plug:      { build: buildSparkPlug,      pos: [1.9, 12.3, 0],  explode: [5, 14, 0],     enter: [7, 18, 0] },
};

// Generic shapes for parts recovered from a document we have no model for.
// On an arbitrary manual this is most of them, and a part with no geometry is
// still a real part of the procedure -- dropping it would silently shorten the
// job. These are deliberately plain: they must never be mistaken for CAD.
const GENERIC_MATERIAL = mat(0x6d7683, 0.65, 0.35);

const SHAPE_RULES = [
  [/(bolt|screw|stud)/,               () => hexBolt(0.17, 2.0, 0.36, 0.3)],
  [/(nut)/,                           () => shape(new THREE.CylinderGeometry(0.5, 0.5, 0.4, 6))],
  [/(circlip|washer|shim)/,           () => shape(new THREE.TorusGeometry(0.7, 0.09, 8, 40))],
  [/(ring|seal|gasket|keeper|collet)/,() => shape(new THREE.TorusGeometry(0.9, 0.14, 10, 44))],
  [/(spring)/,                        () => shape(coilSpring(0.42, 1.8, 7))],
  [/(shaft|pin|rod|spindle|journal|dowel)/, () => shape(rotToX(new THREE.CylinderGeometry(0.34, 0.34, 3.0, 20)))],
  [/(gear|pulley|wheel|rotor|disc)/,  () => shape(rotToX(new THREE.CylinderGeometry(1.5, 1.5, 0.45, 36)))],
  [/(valve|tappet|lifter)/,           () => valve()],
  [/(plate|cover|housing|case|block|body|deck|manifold)/, () => shape(new THREE.BoxGeometry(2.6, 0.7, 2.2))],
];

function shape(geometry) {
  const g = new THREE.Group();
  g.add(new THREE.Mesh(geometry, GENERIC_MATERIAL));
  return g;
}

function buildGeneric(name) {
  const low = String(name || '').toLowerCase();
  for (const [pattern, make] of SHAPE_RULES) {
    if (pattern.test(low)) return make();
  }
  return shape(new THREE.BoxGeometry(1.5, 0.9, 1.1));
}

/**
 * Instantiate one part.
 *
 * A part we model gets its real geometry. A part we do not gets a generic
 * shape chosen from its name, flagged so the viewer can say so out loud.
 * Nothing recovered from a document is ever silently discarded.
 */
export function buildPart(id, name) {
  const spec = PART_LIBRARY[id];
  if (!spec) {
    const group = buildGeneric(name || id);
    group.name = id;
    group.userData.generic = true;
    decorate(group);
    return group;
  }

  const group = spec.build();
  group.name = id;
  group.userData.seated = new THREE.Vector3(...spec.pos);
  group.userData.explode = new THREE.Vector3(...spec.explode);
  group.userData.enter = new THREE.Vector3(...spec.enter);
  group.userData.shell = !!spec.shell;
  group.position.copy(group.userData.seated);
  decorate(group);
  return group;
}

/** Shadows, edge lines and measured extents. Shared by real and generic parts. */
function decorate(group) {
  const meshes = [];
  group.traverse((o) => {
    if (o.isMesh) {
      o.castShadow = true;
      o.receiveShadow = true;
      meshes.push(o);
    }
  });

  // Second pass: children cannot be added during a traverse.
  for (const mesh of meshes) {
    const count = mesh.geometry.getAttribute('position')?.count ?? 0;
    if (count > EDGE_VERTEX_LIMIT) continue;
    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(mesh.geometry, EDGE_ANGLE),
      EDGE_MATERIAL
    );
    edges.raycast = () => {};   // lines must never swallow a part pick
    edges.userData.isEdge = true;
    mesh.add(edges);
  }

  // Half-extent of the part's own volume, measured once. Framing that fits
  // only part origins puts the camera inside the crankcase, because a 9-unit
  // block reports as a single point at the middle of itself.
  const bounds = new THREE.Box3().setFromObject(group);
  group.userData.halfExtent = bounds.getSize(new THREE.Vector3()).multiplyScalar(0.5);
}

export const KNOWN_PART_IDS = Object.keys(PART_LIBRARY);
