/* RangeIQ 3D terrain: USGS 3DEP lidar heights with the NAIP aerial photo draped on top.
   Same approach as the Marfa Lights 3D map (three.js r170, uint16 height grid). Loaded only when the 3D view opens.
   Scene units: the ranch's longest side = 1. x east, z south (north is -z), y up. */
import * as THREE from "three";
import {OrbitControls} from "./vendor/three/OrbitControls.js";

const STATUS_COLOR = {good: 0x2e9d55, watch: 0xf0b429, act: 0xe5483b, unknown: 0xdddddd};

export function mount(container, {meta, height, texture, statusById = {}, namesById = {}, focusId = null, exaggeration = 2}) {
  const NX = meta.nx, NY = meta.ny, W = meta.width_m, H = meta.height_m, CELL = meta.cell_m;
  const S = 1 / Math.max(W, H);
  const q = new Uint16Array(height);
  const elev = new Float32Array(NX * NY);
  let zmin = Infinity;
  for (let i = 0; i < elev.length; i++) { elev[i] = meta.z0 + q[i] * meta.zscale; if (elev[i] < zmin) zmin = elev[i]; }
  let exag = exaggeration;

  let renderer;
  try { renderer = new THREE.WebGLRenderer({antialias: true, alpha: false}); }
  catch (e) { container.innerHTML = "<p class='dim' style='padding:16px'>3D needs WebGL, which this browser has turned off. The map view has the same pastures.</p>"; return {dispose() {}, setExaggeration() {}, reset() {}}; }
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  container.innerHTML = ""; container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xcfe3f2);
  const camera = new THREE.PerspectiveCamera(45, 1, 0.001, 20);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true; controls.maxPolarAngle = Math.PI * 0.47; controls.minDistance = 0.05; controls.maxDistance = 6;
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8a7a5a, 1.6));
  const sun = new THREE.DirectionalLight(0xffffff, 1.4); sun.position.set(-1, 1.2, -0.8); scene.add(sun);

  // terrain mesh
  const geo = new THREE.PlaneGeometry(W * S, H * S, NX - 1, NY - 1);
  geo.rotateX(-Math.PI / 2);                  // plane row 0 (top) -> north (-z)
  const pos = geo.attributes.position;
  function applyHeights() {
    for (let i = 0; i < pos.count; i++) pos.setY(i, (elev[i] - zmin) * exag * S);
    pos.needsUpdate = true; geo.computeVertexNormals(); geo.computeBoundingSphere();
  }
  applyHeights();
  const blobUrl = URL.createObjectURL(new Blob([texture.bytes], {type: texture.mime}));
  const tex = new THREE.TextureLoader().load(blobUrl, () => URL.revokeObjectURL(blobUrl));
  tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  const mesh = new THREE.Mesh(geo, new THREE.MeshLambertMaterial({map: tex}));
  scene.add(mesh);

  // pasture outlines draped on the surface
  function elevAt(x, y) {                     // x east, y north from SW corner (m); bilinear on the grid
    const c = Math.min(Math.max(x / CELL, 0), NX - 1.001), r = Math.min(Math.max((H - y) / CELL, 0), NY - 1.001);
    const c0 = Math.floor(c), r0 = Math.floor(r), fc = c - c0, fr = r - r0, i = r0 * NX + c0;
    return (elev[i] * (1 - fc) + elev[i + 1] * fc) * (1 - fr) + (elev[i + NX] * (1 - fc) + elev[i + NX + 1] * fc) * fr;
  }
  const outlines = new THREE.Group(); scene.add(outlines);
  const labels = new THREE.Group(); scene.add(labels);
  function label(text, color) {
    const c = document.createElement("canvas"), g = c.getContext("2d"), f = 36;
    g.font = `700 ${f}px system-ui, sans-serif`; const w = Math.ceil(g.measureText(text).width) + 28;
    c.width = w; c.height = f + 22;
    g.fillStyle = "rgba(255,250,242,.92)"; g.strokeStyle = "#" + color.toString(16).padStart(6, "0"); g.lineWidth = 6;
    g.beginPath(); g.roundRect(3, 3, w - 6, f + 16, 12); g.fill(); g.stroke();
    g.fillStyle = "#1d150f"; g.font = `700 ${f}px system-ui, sans-serif`; g.textBaseline = "middle"; g.fillText(text, 14, (f + 22) / 2);
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({map: new THREE.CanvasTexture(c), depthTest: false}));
    sp.userData.aspect = w / (f + 22); sp.renderOrder = 10; return sp;
  }
  function drawOutlines() {
    outlines.clear(); labels.clear();
    const lift = 3 * exag * S + 0.0015;
    for (const o of meta.outlines) {
      const color = STATUS_COLOR[statusById[o.id]] ?? 0xffffff;
      const pts = [];
      for (let k = 0; k < o.ring.length - 1; k++) {           // densify so the line follows the ground
        const [x0, y0] = o.ring[k], [x1, y1] = o.ring[k + 1];
        const n = Math.max(1, Math.ceil(Math.hypot(x1 - x0, y1 - y0) / (CELL * 1.5)));
        for (let t = 0; t < n; t++) { const x = x0 + (x1 - x0) * t / n, y = y0 + (y1 - y0) * t / n;
          pts.push(new THREE.Vector3((x - W / 2) * S, (elevAt(x, y) - zmin) * exag * S + lift, (H / 2 - y) * S)); }
      }
      const wide = o.id === focusId;
      // WebGL ignores line width, so draw the outline as a thin tube that stays visible on a phone.
      const radius = (wide ? 0.006 : 0.0035) * Math.max(1, Math.sqrt(W * H) * S);
      const curve = new THREE.CatmullRomCurve3(pts, true, "centripetal", 0);
      const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, Math.min(pts.length * 2, 1200), radius, 5, true),
        new THREE.MeshBasicMaterial({color, depthTest: true}));
      tube.renderOrder = 5; outlines.add(tube);
      // label at the ring's average point
      let sx = 0, sy = 0; o.ring.forEach(([x, y]) => { sx += x; sy += y; }); sx /= o.ring.length; sy /= o.ring.length;
      if (meta.outlines.length <= 25 || wide) {
        const sp = label(namesById[o.id] || o.name, color);
        sp.position.set((sx - W / 2) * S, (elevAt(sx, sy) - zmin) * exag * S + lift + 0.04, (H / 2 - sy) * S);
        labels.add(sp);
      }
    }
  }
  drawOutlines();

  // camera framing
  const relief = ((meta.z_max_m ?? zmin) - zmin) * S;
  function fitDistance(spanX, spanZ) {
    // distance at which a spanX x spanZ footprint fits the screen, for this aspect ratio
    const aspect = Math.max(camera.aspect, 0.3), vfov = THREE.MathUtils.degToRad(camera.fov);
    const hfov = 2 * Math.atan(Math.tan(vfov / 2) * aspect);
    return 1.12 * Math.max((spanX / 2) / Math.tan(hfov / 2), (spanZ / 2) / Math.tan(vfov / 2));
  }
  function reset() {
    let target = new THREE.Vector3(0, relief * exag / 2, 0), dist = fitDistance(W * S, H * S);
    const f = focusId && meta.outlines.find(o => o.id === focusId);
    if (f) {
      const xs = f.ring.map(p => p[0]), ys = f.ring.map(p => p[1]);
      const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2;
      target = new THREE.Vector3((cx - W / 2) * S, (elevAt(cx, cy) - zmin) * exag * S, (H / 2 - cy) * S);
      dist = Math.max(0.08, fitDistance((Math.max(...xs) - Math.min(...xs)) * S * 2.2, (Math.max(...ys) - Math.min(...ys)) * S * 2.2));
    }
    controls.target.copy(target);
    const dir = new THREE.Vector3(-0.3, 0.62, 0.72).normalize();   // from the south-south-west, looking down ~40 degrees
    camera.position.copy(target).addScaledVector(dir, dist);
    controls.update();
  }
  function resize() {
    const w = container.clientWidth, h = container.clientHeight;
    renderer.setSize(w, h, false); camera.aspect = w / Math.max(h, 1); camera.updateProjectionMatrix();
    renderer.domElement.style.width = "100%"; renderer.domElement.style.height = "100%";
  }
  let first = true;
  const ro = new ResizeObserver(() => { resize(); if (first) { first = false; reset(); } }); ro.observe(container); resize(); reset();

  let running = true;
  (function loop() {
    if (!running) return;
    controls.update();
    labels.children.forEach(sp => { const d = camera.position.distanceTo(sp.position); sp.scale.set(0.045 * d * sp.userData.aspect, 0.045 * d, 1); });
    renderer.render(scene, camera);
    requestAnimationFrame(loop);
  })();

  return {
    setExaggeration(v) { exag = v; applyHeights(); drawOutlines(); },
    reset,
    dispose() { running = false; ro.disconnect(); controls.dispose(); geo.dispose(); tex.dispose(); renderer.dispose(); container.innerHTML = ""; }
  };
}
