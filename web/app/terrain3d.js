/* RangeIQ 3D terrain: USGS 3DEP lidar heights, with either the NAIP aerial photo or a topo map draped on top.
   Pasture boundaries are glowing walls that fade upward, colored by status. Photos taken with the app stand on the ground as pins.
   three.js r170, loaded only when the 3D view opens.
   Scene units: the ranch's longest side = 1. x east, z south (north is -z), y up. */
import * as THREE from "three";
import {OrbitControls} from "./vendor/three/OrbitControls.js";

const GLOW = {good: 0x4dff9a, watch: 0xffc23d, act: 0xff4a3a, unknown: 0xbfe2ff};
const D2R = Math.PI / 180;

// WGS84 lat/lon -> UTM metres (Snyder 1987, USGS Prof. Paper 1395, eqs. 8-9 to 8-10). Sub-metre within a zone.
export function toUTM(lat, lon, zone, south) {
  const a = 6378137, f = 1 / 298.257223563, k0 = 0.9996, e2 = f * (2 - f), ep2 = e2 / (1 - e2);
  const phi = lat * D2R, lam = lon * D2R, lam0 = ((zone - 1) * 6 - 180 + 3) * D2R;
  const s = Math.sin(phi), c = Math.cos(phi), t = Math.tan(phi);
  const N = a / Math.sqrt(1 - e2 * s * s), T = t * t, C = ep2 * c * c, A = c * (lam - lam0);
  const e4 = e2 * e2, e6 = e4 * e2;
  const M = a * ((1 - e2 / 4 - 3 * e4 / 64 - 5 * e6 / 256) * phi - (3 * e2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024) * Math.sin(2 * phi)
    + (15 * e4 / 256 + 45 * e6 / 1024) * Math.sin(4 * phi) - (35 * e6 / 3072) * Math.sin(6 * phi));
  const x = k0 * N * (A + (1 - T + C) * A ** 3 / 6 + (5 - 18 * T + T * T + 72 * C - 58 * ep2) * A ** 5 / 120) + 500000;
  let y = k0 * (M + N * t * (A * A / 2 + (5 - T + 9 * C + 4 * C * C) * A ** 4 / 24 + (61 - 58 * T + T * T + 600 * C - 330 * ep2) * A ** 6 / 720));
  if (south) y += 10000000;
  return [x, y];
}

const WALL_VERT = `
  attribute float v;
  varying float vV;
  void main() { vV = v; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;
const WALL_FRAG = `
  uniform vec3 color; uniform float time; uniform float strength;
  varying float vV;
  void main() {
    float fade = pow(1.0 - vV, 1.25);                              // bright at the ground, gone at the top
    float shimmer = 0.82 + 0.18 * sin(vV * 18.0 - time * 2.2);    // soft bands drifting upward
    float base = smoothstep(0.10, 0.0, vV);                       // hot line where the wall meets the ground
    float a = clamp((fade * shimmer * 0.95 + base * 0.9) * strength, 0.0, 1.0);
    gl_FragColor = vec4(mix(color, vec3(1.0), base * 0.45) * a, a);
  }`;

export function mount(container, {meta, height, texture, statusById = {}, namesById = {}, lonlatById = {}, focusId = null,
  exaggeration = 2, look = "photo", photos = [], onPhoto = () => {}, onPasture = () => {}}) {
  const NX = meta.nx, NY = meta.ny, W = meta.width_m, H = meta.height_m, CELL = meta.cell_m;
  const S = 1 / Math.max(W, H);
  const q = new Uint16Array(height);
  const elev = new Float32Array(NX * NY);
  let zmin = Infinity, zmax = -Infinity;
  for (let i = 0; i < elev.length; i++) { const z = meta.z0 + q[i] * meta.zscale; elev[i] = z; if (z < zmin) zmin = z; if (z > zmax) zmax = z; }
  let exag = exaggeration;

  let renderer;
  try { renderer = new THREE.WebGLRenderer({antialias: true, alpha: true}); }
  catch (e) {
    container.innerHTML = "<div class='busy'>3D needs WebGL, which this browser has turned off. The Map view has the same pastures.</div>";
    return {dispose() {}, setExaggeration() {}, reset() {}, setLook() {}, setPhotos() {}};
  }
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.setClearColor(0x000000, 0);                   // the evening sky is a CSS gradient behind the canvas
  container.innerHTML = ""; container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0xe2a77e, 2.2, 7);          // warm haze far away
  const camera = new THREE.PerspectiveCamera(45, 1, 0.001, 20);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true; controls.maxPolarAngle = Math.PI * 0.47; controls.minDistance = 0.05; controls.maxDistance = 6;
  scene.add(new THREE.HemisphereLight(0xeef0ff, 0x7a5a3a, 1.9));
  const sun = new THREE.DirectionalLight(0xffd9b0, 1.6); sun.position.set(-1.2, 0.7, 0.4); scene.add(sun);   // low sun from the west

  // ---------------------------------------------------------------- ground
  const geo = new THREE.PlaneGeometry(W * S, H * S, NX - 1, NY - 1);
  geo.rotateX(-Math.PI / 2);                  // plane row 0 (top) -> north (-z)
  const pos = geo.attributes.position;
  function applyHeights() {
    for (let i = 0; i < pos.count; i++) pos.setY(i, (elev[i] - zmin) * exag * S);
    pos.needsUpdate = true; geo.computeVertexNormals(); geo.computeBoundingSphere();
  }
  applyHeights();
  const blobUrl = URL.createObjectURL(new Blob([texture.bytes], {type: texture.mime || "image/jpeg"}));
  const photoTex = new THREE.TextureLoader().load(blobUrl, () => URL.revokeObjectURL(blobUrl));
  photoTex.colorSpace = THREE.SRGBColorSpace; photoTex.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  const photoMat = new THREE.MeshLambertMaterial({map: photoTex});
  let topoMat = null;
  const mesh = new THREE.Mesh(geo, photoMat);
  scene.add(mesh);

  function gridZ(c, r) {                      // bilinear elevation at fractional grid column/row
    c = Math.min(Math.max(c, 0), NX - 1.001); r = Math.min(Math.max(r, 0), NY - 1.001);
    const c0 = Math.floor(c), r0 = Math.floor(r), fc = c - c0, fr = r - r0, i = r0 * NX + c0;
    return (elev[i] * (1 - fc) + elev[i + 1] * fc) * (1 - fr) + (elev[i + NX] * (1 - fc) + elev[i + NX + 1] * fc) * fr;
  }
  const elevAt = (x, y) => gridZ(x / CELL, (H - y) / CELL);   // x east, y north from the SW corner (m)
  const toScene = (x, y, lift = 0) => new THREE.Vector3((x - W / 2) * S, (elevAt(x, y) - zmin) * exag * S + lift, (H / 2 - y) * S);

  // Topo look: earth-tone elevation colors, hillshade from the NW, and contour lines every "nice" interval in feet.
  function buildTopo() {
    const scale = Math.max(1, Math.min(4, Math.floor(1024 / Math.max(NX, NY))));
    const TW = (NX - 1) * scale + 1, TH = (NY - 1) * scale + 1;
    const z = new Float32Array(TW * TH);
    for (let r = 0; r < TH; r++) for (let c = 0; c < TW; c++) z[r * TW + c] = gridZ(c / scale, r / scale);
    const reliefFt = (zmax - zmin) * 3.28084;
    const ci = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500].find(v => reliefFt / v <= 14) || 1000;   // contour interval (ft)
    const stops = [[0, [122, 146, 96]], [0.3, [168, 170, 112]], [0.55, [201, 178, 124]], [0.8, [168, 118, 76]], [1, [232, 220, 196]]];
    const ramp = t => { for (let k = 1; k < stops.length; k++) if (t <= stops[k][0]) {
      const [t0, a] = stops[k - 1], [t1, b] = stops[k], u = (t - t0) / (t1 - t0 || 1); return a.map((v, j) => v + (b[j] - v) * u); } return stops[4][1]; };
    const cv = document.createElement("canvas"); cv.width = TW; cv.height = TH;
    const g = cv.getContext("2d"), img = g.createImageData(TW, TH), d = img.data;
    const px = CELL / scale, az = 315 * D2R, alt = 40 * D2R, span = (zmax - zmin) || 1;
    const band = v => Math.floor((v - zmin) * 3.28084 / ci);
    for (let r = 0; r < TH; r++) for (let c = 0; c < TW; c++) {
      const i = r * TW + c, zc = z[i];
      const zl = z[r * TW + Math.max(c - 1, 0)], zr = z[r * TW + Math.min(c + 1, TW - 1)];
      const zu = z[Math.max(r - 1, 0) * TW + c], zd = z[Math.min(r + 1, TH - 1) * TW + c];
      const dzdx = (zr - zl) / (2 * px), dzdy = (zu - zd) / (2 * px);           // y north
      const slope = Math.atan(Math.hypot(dzdx, dzdy)), aspect = Math.atan2(dzdy, -dzdx);
      const shade = Math.max(0, Math.cos(alt) * Math.cos(slope) + Math.sin(alt) * Math.sin(slope) * Math.cos(az - aspect));
      const col = ramp((zc - zmin) / span), k = 0.55 + 0.6 * shade;
      let [R, G, B] = col.map(v => v * k);
      const b0 = band(zc);
      if (c + 1 < TW && r + 1 < TH && (band(z[i + 1]) !== b0 || band(z[i + TW]) !== b0)) {
        const index = Math.max(b0, band(z[i + 1]), band(z[i + TW])) % 5 === 0;
        const m = index ? 0.35 : 0.62; R *= m; G *= m; B *= m;
      }
      d[i * 4] = Math.min(255, R); d[i * 4 + 1] = Math.min(255, G); d[i * 4 + 2] = Math.min(255, B); d[i * 4 + 3] = 255;
    }
    g.putImageData(img, 0, 0);
    const t = new THREE.CanvasTexture(cv); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = photoTex.anisotropy;
    topoMat = new THREE.MeshBasicMaterial({map: t});        // shading is baked in, like a paper topo map
    topoMat.userData.interval = ci;
  }
  function setLook(v) {
    look = v === "topo" ? "topo" : "photo";
    if (look === "topo" && !topoMat) buildTopo();
    mesh.material = look === "topo" ? topoMat : photoMat;
  }
  setLook(look);

  // ---------------------------------------------------------------- glowing boundary walls
  const walls = new THREE.Group(), labels = new THREE.Group();
  scene.add(walls); scene.add(labels);
  const wallMats = [];
  function label(text, color) {
    const c = document.createElement("canvas"), g = c.getContext("2d"), f = 36;
    g.font = `700 ${f}px system-ui, sans-serif`; const w = Math.ceil(g.measureText(text).width) + 30;
    c.width = w; c.height = f + 22;
    g.fillStyle = "rgba(20,22,40,.78)"; g.strokeStyle = "#" + color.toString(16).padStart(6, "0"); g.lineWidth = 5;
    g.beginPath(); g.roundRect(3, 3, w - 6, f + 16, 14); g.fill(); g.stroke();
    g.fillStyle = "#fff"; g.font = `700 ${f}px system-ui, sans-serif`; g.textBaseline = "middle"; g.fillText(text, 15, (f + 22) / 2);
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({map: new THREE.CanvasTexture(c), depthTest: false}));
    sp.userData.aspect = w / (f + 22); sp.userData.k = 0.045; sp.renderOrder = 10; return sp;
  }
  function densify(ring) {
    const out = [];
    for (let k = 0; k < ring.length - 1; k++) {
      const [x0, y0] = ring[k], [x1, y1] = ring[k + 1];
      const n = Math.max(1, Math.ceil(Math.hypot(x1 - x0, y1 - y0) / (CELL * 1.5)));
      for (let t = 0; t < n; t++) out.push([x0 + (x1 - x0) * t / n, y0 + (y1 - y0) * t / n]);
    }
    out.push(ring[ring.length - 1]);
    return out;
  }
  function drawWalls() {
    walls.children.forEach(o => o.geometry.dispose()); walls.clear();
    labels.children.forEach(o => { o.material.map.dispose(); o.material.dispose(); }); labels.clear();
    wallMats.forEach(m => m.dispose()); wallMats.length = 0;
    const wallH = 0.065;                       // ~6% of the ranch's long side, whatever the height setting
    for (const o of meta.outlines) {
      const status = statusById[o.id] || "unknown", color = GLOW[status] ?? GLOW.unknown, focus = o.id === focusId;
      const pts = densify(o.ring), h = wallH * (focus ? 1.6 : 1) * (status === "act" ? 1.3 : 1);
      const P = new Float32Array(pts.length * 6), V = new Float32Array(pts.length * 2), idx = [];
      pts.forEach(([x, y], k) => {
        const b = toScene(x, y, 0.0008);
        P.set([b.x, b.y, b.z, b.x, b.y + h, b.z], k * 6); V[k * 2] = 0; V[k * 2 + 1] = 1;
        if (k < pts.length - 1) { const a = k * 2; idx.push(a, a + 2, a + 1, a + 1, a + 2, a + 3); }
      });
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(P, 3)); g.setAttribute("v", new THREE.BufferAttribute(V, 1)); g.setIndex(idx);
      const mat = new THREE.ShaderMaterial({vertexShader: WALL_VERT, fragmentShader: WALL_FRAG, transparent: true, depthWrite: false,
        side: THREE.DoubleSide, blending: THREE.AdditiveBlending,
        uniforms: {color: {value: new THREE.Color(color)}, time: {value: 0}, strength: {value: status === "act" ? 1.25 : 1}}});
      mat.userData.pulse = status === "act";
      wallMats.push(mat);
      const wall = new THREE.Mesh(g, mat); wall.renderOrder = 4; walls.add(wall);
      // a solid bright line on the ground so the boundary reads from straight above too
      const line = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts.map(([x, y]) => toScene(x, y, 0.001)), true, "centripetal", 0),
        Math.min(pts.length * 2, 1200), 0.0022 * (focus ? 1.6 : 1), 5, true), new THREE.MeshBasicMaterial({color, fog: false}));
      line.renderOrder = 5; walls.add(line);
      if (meta.outlines.length <= 25 || focus) {
        let sx = 0, sy = 0; o.ring.forEach(([x, y]) => { sx += x; sy += y; }); sx /= o.ring.length; sy /= o.ring.length;
        const sp = label(namesById[o.id] || o.name, color); sp.position.copy(toScene(sx, sy, wallH + 0.03)); labels.add(sp);
      }
    }
  }
  drawWalls();

  // ---------------------------------------------------------------- photo pins (GPS + compass direction)
  const zoneMatch = /^32([67])(\d\d)$/.exec(String(meta.crs_epsg || ""));
  let origin = meta.origin_x != null ? [meta.origin_x, meta.origin_y] : null;
  if (!origin && zoneMatch) {                 // older terrain files: register a pasture corner instead
    const o = meta.outlines.find(x => (lonlatById[x.id] || []).length);
    if (o) { const [lon, lat] = lonlatById[o.id][0], [ux, uy] = toUTM(lat, lon, +zoneMatch[2], zoneMatch[1] === "7"); origin = [ux - o.ring[0][0], uy - o.ring[0][1]]; }
  }
  const localXY = (lat, lon) => {
    if (!zoneMatch || !origin) return null;
    const [ux, uy] = toUTM(lat, lon, +zoneMatch[2], zoneMatch[1] === "7");
    const x = ux - origin[0], y = uy - origin[1];
    return x >= 0 && y >= 0 && x <= W && y <= H ? [x, y] : null;
  };
  const pins = new THREE.Group(); scene.add(pins);
  const pinTex = {};
  function pinTexture(flag, icon = "📷") {
    const key = (flag ? "f" : "n") + icon;
    if (pinTex[key]) return pinTex[key];
    const c = document.createElement("canvas"); c.width = c.height = 96; const g = c.getContext("2d");
    g.fillStyle = flag ? "#d63c2f" : "#ffffff"; g.strokeStyle = flag ? "#fff" : "#1d2a44"; g.lineWidth = 6;
    g.beginPath(); g.arc(48, 48, 40, 0, Math.PI * 2); g.fill(); g.stroke();
    g.font = "44px system-ui, 'Apple Color Emoji', 'Segoe UI Emoji'"; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(icon, 48, 52);
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return (pinTex[key] = t);
  }
  let photoList = photos;
  function drawPins() {
    pins.children.forEach(o => { if (o.geometry) o.geometry.dispose(); if (o.material && !o.isSprite) o.material.dispose(); }); pins.clear();
    for (const p of photoList) {
      if (p.lat == null) continue;
      const xy = localXY(p.lat, p.lon); if (!xy) continue;
      const ground = toScene(xy[0], xy[1], 0.001), top = ground.clone(); top.y += 0.035;
      const stem = new THREE.Line(new THREE.BufferGeometry().setFromPoints([ground, top]), new THREE.LineBasicMaterial({color: 0xffffff, fog: false}));
      pins.add(stem);
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({map: pinTexture(!!p.flagged, p.icon || "📷"), depthTest: false}));
      sp.position.copy(top); sp.userData = {photo: p.client_id, k: 0.042, aspect: 1}; sp.renderOrder = 12; pins.add(sp);
      if (p.heading_deg != null) {            // a flat wedge on the ground pointing where the camera faced
        const th = (90 - p.heading_deg) * D2R, wedge = new THREE.CircleGeometry(0.03, 12, th - 0.5, 1.0);
        wedge.rotateX(-Math.PI / 2);
        const m = new THREE.Mesh(wedge, new THREE.MeshBasicMaterial({color: p.flagged ? 0xff6b5a : 0xffffff, transparent: true, opacity: 0.55, depthWrite: false, fog: false}));
        m.position.copy(ground); m.position.y += 0.0015; m.renderOrder = 6; pins.add(m);
      }
    }
  }
  drawPins();

  // ---------------------------------------------------------------- tap: photo pin first, then pasture under the finger
  const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
  let down = null;
  renderer.domElement.addEventListener("pointerdown", e => { down = [e.clientX, e.clientY]; });
  renderer.domElement.addEventListener("pointerup", e => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 8) return;
    const r = renderer.domElement.getBoundingClientRect();
    ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    const hitPin = ray.intersectObjects(pins.children.filter(o => o.isSprite))[0];
    if (hitPin) { onPhoto(hitPin.object.userData.photo); return; }
    const hit = ray.intersectObject(mesh)[0]; if (!hit) return;
    const x = hit.point.x / S + W / 2, y = H / 2 - hit.point.z / S;
    for (const o of meta.outlines) {
      let inside = false; const ring = o.ring;
      for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const [xi, yi] = ring[i], [xj, yj] = ring[j];
        if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
      }
      if (inside) { onPasture(o.id); return; }
    }
  });

  // ---------------------------------------------------------------- camera framing
  function fitDistance(spanX, spanZ) {
    const aspect = Math.max(camera.aspect, 0.3), vfov = THREE.MathUtils.degToRad(camera.fov);
    const hfov = 2 * Math.atan(Math.tan(vfov / 2) * aspect);
    return 1.12 * Math.max((spanX / 2) / Math.tan(hfov / 2), (spanZ / 2) / Math.tan(vfov / 2));
  }
  function reset() {
    let target = new THREE.Vector3(0, (zmax - zmin) * S * exag / 2, 0), dist = fitDistance(W * S, H * S);
    const f = focusId && meta.outlines.find(o => o.id === focusId);
    if (f) {
      const xs = f.ring.map(p => p[0]), ys = f.ring.map(p => p[1]);
      const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2;
      target = toScene(cx, cy);
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
  const clock = new THREE.Clock();
  (function loop() {
    if (!running) return;
    const t = clock.getElapsedTime();
    controls.update();
    wallMats.forEach(m => { m.uniforms.time.value = t; if (m.userData.pulse) m.uniforms.strength.value = 1.15 + 0.25 * Math.sin(t * 3); });
    for (const sp of [...labels.children, ...pins.children.filter(o => o.isSprite)]) {
      const d = camera.position.distanceTo(sp.position), k = sp.userData.k; sp.scale.set(k * d * sp.userData.aspect, k * d, 1);
    }
    renderer.render(scene, camera);
    requestAnimationFrame(loop);
  })();

  return {
    setExaggeration(v) { exag = v; applyHeights(); drawWalls(); drawPins(); },
    setLook,
    contourFt: () => topoMat && topoMat.userData.interval,
    setPhotos(list) { photoList = list || []; drawPins(); },
    reset,
    dispose() {
      running = false; ro.disconnect(); controls.dispose();
      walls.children.forEach(o => o.geometry.dispose()); wallMats.forEach(m => m.dispose());
      geo.dispose(); photoTex.dispose(); photoMat.dispose(); if (topoMat) { topoMat.map.dispose(); topoMat.dispose(); }
      Object.values(pinTex).forEach(t => t.dispose()); renderer.dispose(); container.innerHTML = "";
    }
  };
}
