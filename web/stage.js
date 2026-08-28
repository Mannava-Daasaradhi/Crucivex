/**
 * The stage: renderer, camera, lighting and ground.
 *
 * Everything here is fixed set dressing — it does not depend on which document
 * is loaded, and nothing in it should. Split out of app.js so that file is
 * about compiling an IR into a scene rather than about configuring WebGL.
 *
 * The visual language is inspection software, not photorealism: a neutral
 * studio environment, one hard key for edge definition, and a cool rim so
 * silhouettes separate from the background.
 */

import * as THREE from './vendor/three.module.js';
import { OrbitControls } from './vendor/OrbitControls.js';
import { RoomEnvironment } from './vendor/RoomEnvironment.js';

export const container = document.getElementById('viewport');
export const scene = new THREE.Scene();

export const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 500);
camera.position.set(18, 13, 20);

// alpha:true so the CSS gradient behind the canvas becomes the backdrop.
export const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.15;
container.appendChild(renderer.domElement);

export const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.06;
controls.target.set(0, 6, 0);
controls.maxDistance = 90;
controls.minDistance = 5;

const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
scene.environmentIntensity = 0.55;

const key = new THREE.DirectionalLight(0xffffff, 2.1);
key.position.set(14, 22, 12);
key.castShadow = true;
key.shadow.mapSize.set(2048, 2048);
key.shadow.camera.near = 1;
key.shadow.camera.far = 80;
key.shadow.camera.left = -26;
key.shadow.camera.right = 26;
key.shadow.camera.top = 30;
key.shadow.camera.bottom = -16;
key.shadow.bias = -0.0009;
scene.add(key);

const rim = new THREE.DirectionalLight(0x7fc0ff, 1.35);
rim.position.set(-16, 9, -14);
scene.add(rim);
scene.add(new THREE.HemisphereLight(0xa8c2dd, 0x161a21, 0.65));

const grid = new THREE.GridHelper(140, 70, 0x27303d, 0x171d26);
grid.position.y = -7;
grid.material.transparent = true;
grid.material.opacity = 0.5;
scene.add(grid);

const floor = new THREE.Mesh(
  new THREE.PlaneGeometry(220, 220),
  new THREE.ShadowMaterial({ opacity: 0.38 })
);
floor.rotation.x = -Math.PI / 2;
floor.position.y = -6.99;
floor.receiveShadow = true;
scene.add(floor);

/** Everything decoded from the document hangs off this group. */
export const assembly = new THREE.Group();
scene.add(assembly);
