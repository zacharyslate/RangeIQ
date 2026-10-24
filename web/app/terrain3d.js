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

// UTM metres -> WGS84 lat/lon (Snyder 1987, eqs. 8-12 to 8-25). Used to turn a tap on the 3D ground into a GPS point.
export function fromUTM(x, y, zone, south) {
  const a = 6378137, f = 1 / 298.257223563, k0 = 0.9996, e2 = f * (2 - f), ep2 = e2 / (1 - e2);
  const e1 = (1 - Math.sqrt(1 - e2)) / (1 + Math.sqrt(1 - e2)), lam0 = ((zone - 1) * 6 - 180 + 3) * D2R;
  const M = (south ? y - 10000000 : y) / k0;
  const mu = M / (a * (1 - e2 / 4 - 3 * e2 * e2 / 64 - 5 * e2 ** 3 / 256));
  const phi1 = mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * Math.sin(2 * mu) + (21 * e1 * e1 / 16 - 55 * e1 ** 4 / 32) * Math.sin(4 * mu)
    + (151 * e1 ** 3 / 96) * Math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * Math.sin(8 * mu);
  const s1 = Math.sin(phi1), c1 = Math.cos(phi1), t1 = Math.tan(phi1);
  const C1 = ep2 * c1 * c1, T1 = t1 * t1, N1 = a / Math.sqrt(1 - e2 * s1 * s1), R1 = a * (1 - e2) / (1 - e2 * s1 * s1) ** 1.5;
  const D = (x - 500000) / (N1 * k0);
  const lat = phi1 - (N1 * t1 / R1) * (D * D / 2 - (5 + 3 * T1 + 10 * C1 - 4 * C1 * C1 - 9 * ep2) * D ** 4 / 24
    + (61 + 90 * T1 + 298 * C1 + 45 * T1 * T1 - 252 * ep2 - 3 * C1 * C1) * D ** 6 / 720);
  const lon = lam0 + (D - (1 + 2 * T1 + C1) * D ** 3 / 6 + (5 - 2 * C1 + 28 * T1 - 3 * C1 * C1 + 8 * ep2 + 24 * T1 * T1) * D ** 5 / 120) / c1;
  return [lat / D2R, lon / D2R];
}

// Walls and lines are sized on screen, not on the ground: their height and thickness follow the camera distance
// (uniforms updated every frame), so they stay readable zoomed out and get out of the way zoomed in.

// A point well inside a pasture for its flag: the centroid when it's inside, otherwise the middle of the widest
// stretch across the shape (U- and L-shaped pastures have their centroid outside).
export function interiorPoint(ring) {
  const pts = ring.length > 1 && ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1] ? ring.slice(0, -1) : ring;
  let a = 0, cx = 0, cy = 0;
  for (let i = 0; i < pts.length; i++) {
    const [x0, y0] = pts[i], [x1, y1] = pts[(i + 1) % pts.length], k = x0 * y1 - x1 * y0;
    a += k; cx += (x0 + x1) * k; cy += (y0 + y1) * k;
  }
  if (a !== 0) { cx /= 3 * a; cy /= 3 * a; } else { cx = pts.reduce((s, p) => s + p[0], 0) / pts.length; cy = pts.reduce((s, p) => s + p[1], 0) / pts.length; }
  const inside = (x, y) => { let c = false; for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const [xi, yi] = pts[i], [xj, yj] = pts[j]; if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) c = !c; } return c; };
  if (inside(cx, cy)) return [cx, cy];
  const ys = pts.map(p => p[1]), y0 = Math.min(...ys), y1 = Math.max(...ys);
  let best = null, bestW = -1;
  for (const f of [0.5, 0.35, 0.65, 0.2, 0.8]) {
    const y = y0 + (y1 - y0) * f, xs = [];
    for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
      const [xi, yi] = pts[i], [xj, yj] = pts[j];
      if ((yi > y) !== (yj > y)) xs.push(xi + (y - yi) * (xj - xi) / (yj - yi));
    }
    xs.sort((p, q) => p - q);
    for (let k = 0; k + 1 < xs.length; k += 2) if (xs[k + 1] - xs[k] > bestW) { bestW = xs[k + 1] - xs[k]; best = [(xs[k] + xs[k + 1]) / 2, y]; }
  }
  return best || [cx, cy];
}

const WALL_VERT = `
  attribute float v;
  uniform float uHeight;
  varying float vV;
  void main() { vV = v; vec3 p = position; p.y += v * uHeight; gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0); }`;
// A tube built with radius R0, redrawn at radius uRadius: the centre line is position - normal * R0.
const TUBE_R0 = 0.001;
const TUBE_VERT = `
  uniform float uRadius;
  void main() { vec3 c = position - normal * ${TUBE_R0.toFixed(4)}; gl_Position = projectionMatrix * modelViewMatrix * vec4(c + normal * uRadius, 1.0); }`;
const TUBE_FRAG = `uniform vec3 color; void main() { gl_FragColor = vec4(color, 1.0); }`;
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
  if (q.length !== NX * NY) throw new Error(`3D files don't match (${q.length} heights for a ${NX}×${NY} grid)`);
  const elev = new Float32Array(NX * NY);
  let zmin = Infinity, zmax = -Infinity;
  for (let i = 0; i < elev.length; i++) { const z = meta.z0 + q[i] * meta.zscale; elev[i] = z; if (z < zmin) zmin = z; if (z > zmax) zmax = z; }
  let exag = exaggeration, exagPending = false;

  let renderer;
  try { renderer = new THREE.WebGLRenderer({antialias: true, alpha: true}); }
  catch (e) {
    const T = (window.RangeI18n && window.RangeI18n.t) || (s => s);
    container.innerHTML = `<div class='busy'>${T("3D needs WebGL, which this browser has turned off. The Map view has the same pastures.")}</div>`;
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
  // "Relief" look: natural West Texas colours from elevation and slope, lit live by the low sun (no contour lines).
  // Grassy flats are sage and gold, slopes turn tan, steep ground and ridges turn rust and grey rock; a little
  // grain keeps it from looking flat. Light and shadow come from the scene's sun, so they change as you turn it.
  function buildTopo() {
    const scale = Math.max(1, Math.min(4, Math.floor(2048 / Math.max(NX, NY))));
    const TW = (NX - 1) * scale + 1, TH = (NY - 1) * scale + 1;
    const z = new Float32Array(TW * TH);
    for (let r = 0; r < TH; r++) for (let c = 0; c < TW; c++) z[r * TW + c] = gridZ(c / scale, r / scale);
    const low = [[0, [104, 128, 78]], [0.35, [150, 152, 92]], [0.6, [192, 168, 110]], [0.85, [170, 120, 80]], [1, [214, 196, 168]]];
    const rock = [138, 112, 92];
    const ramp = t => { for (let k = 1; k < low.length; k++) if (t <= low[k][0]) {
      const [t0, a] = low[k - 1], [t1, b] = low[k], u = (t - t0) / (t1 - t0 || 1); return a.map((v, j) => v + (b[j] - v) * u); } return low[4][1]; };
    const cv = document.createElement("canvas"); cv.width = TW; cv.height = TH;
    const g = cv.getContext("2d"), img = g.createImageData(TW, TH), d = img.data;
    const px = CELL / scale, span = (zmax - zmin) || 1;
    let seed = 1234567;
    const noise = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647 - 0.5; };
    for (let r = 0; r < TH; r++) for (let c = 0; c < TW; c++) {
      const i = r * TW + c, zc = z[i];
      const zl = z[r * TW + Math.max(c - 1, 0)], zr = z[r * TW + Math.min(c + 1, TW - 1)];
      const zu = z[Math.max(r - 1, 0) * TW + c], zd = z[Math.min(r + 1, TH - 1) * TW + c];
      const slopePct = Math.hypot((zr - zl) / (2 * px), (zu - zd) / (2 * px)) * 100;
      const curv = (zl + zr + zu + zd - 4 * zc) / (px * px);          // > 0 in draws and washes, < 0 on ridges
      let col = ramp((zc - zmin) / span);
      const steep = Math.min(1, Math.max(0, (slopePct - 15) / 35));    // 15% slope starts turning rocky, 50% is bare rock
      col = col.map((v, j) => v + (rock[j] - v) * steep);
      if (curv > 0) col = col.map((v, j) => v + ([88, 120, 70][j] - v) * Math.min(0.45, curv * 40));   // greener in the draws
      const grain = 1 + noise() * 0.08;
      d[i * 4] = Math.min(255, col[0] * grain); d[i * 4 + 1] = Math.min(255, col[1] * grain); d[i * 4 + 2] = Math.min(255, col[2] * grain); d[i * 4 + 3] = 255;
    }
    g.putImageData(img, 0, 0);
    const t = new THREE.CanvasTexture(cv); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = photoTex.anisotropy;
    topoMat = new THREE.MeshLambertMaterial({map: t});
  }
  function setLook(v) {
    look = v === "photo" ? "photo" : "relief";
    if (look === "relief" && !topoMat) buildTopo();
    mesh.material = look === "relief" ? topoMat : photoMat;
  }
  setLook(look);

  // ---------------------------------------------------------------- glowing boundary walls
  const walls = new THREE.Group(), labels = new THREE.Group();
  scene.add(walls); scene.add(labels);
  const wallMats = [];
  function label(text, color) {              // a flag: status-coloured pennant + pasture name
    const c = document.createElement("canvas"), g = c.getContext("2d"), f = 36, hex = "#" + color.toString(16).padStart(6, "0");
    g.font = `700 ${f}px system-ui, sans-serif`; const w = Math.ceil(g.measureText(text).width) + 30 + 44;
    c.width = w; c.height = f + 22;
    g.fillStyle = "rgba(20,22,40,.82)"; g.strokeStyle = hex; g.lineWidth = 5;
    g.beginPath(); g.roundRect(3, 3, w - 6, f + 16, 14); g.fill(); g.stroke();
    g.fillStyle = "#fff"; g.fillRect(16, 10, 4, f + 2);                                    // pole
    g.fillStyle = hex; g.beginPath(); g.moveTo(20, 10); g.lineTo(48, 20); g.lineTo(20, 30); g.closePath(); g.fill();   // pennant
    g.fillStyle = "#fff"; g.font = `700 ${f}px system-ui, sans-serif`; g.textBaseline = "middle"; g.fillText(text, 15 + 44, (f + 22) / 2);
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({map: new THREE.CanvasTexture(c), depthTest: false}));
    sp.userData.aspect = w / (f + 22); sp.userData.k = 0.045; sp.renderOrder = 10; return sp;
  }
  // Lines on the ground as straight segments between points. (A smooth spline through the points overshoots wherever
  // two points sit on top of each other, e.g. where a KML ring closes, and draws little loops at the corners.)
  function straightPath(points, closed) {
    const pts = [];
    for (const p of points) if (!pts.length || pts[pts.length - 1].distanceTo(p) > 1e-6) pts.push(p);
    if (closed && pts.length > 2 && pts[0].distanceTo(pts[pts.length - 1]) <= 1e-6) pts.pop();
    if (closed && pts.length > 2) pts.push(pts[0].clone());
    const curve = new THREE.CurvePath();
    for (let i = 1; i < pts.length; i++) curve.add(new THREE.LineCurve3(pts[i - 1], pts[i]));
    return {curve, segments: Math.min(Math.max(pts.length * 2, 8), 3000)};
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
  const lineMats = [], roadMats = [];
  let glowOn = true, flagsOn = true;
  function tubeMaterial(color, widthMul, list = lineMats) {
    const m = new THREE.ShaderMaterial({vertexShader: TUBE_VERT, fragmentShader: TUBE_FRAG,
      uniforms: {color: {value: new THREE.Color(color)}, uRadius: {value: TUBE_R0}}});
    m.userData.widthMul = widthMul; list.push(m); return m;
  }
  // Pasture outlines: from the terrain build at first; the app then hands over the current boundaries (setPastures), so
  // a pasture redrawn a minute ago shows straight away in the same style as the rest instead of waiting for a rebuild.
  let outlines = meta.outlines;
  // Boundaries and lines are draped on the ground point by point. A ring must be closed first, or its last side would be
  // one straight segment cutting through the hills. Parts outside the 3D map (a pasture drawn past its edge, before the
  // server has extended the map) are left out rather than squashed onto the map's edge as straight lines.
  const closeRing = r => r.length > 2 && (r[0][0] !== r[r.length - 1][0] || r[0][1] !== r[r.length - 1][1]) ? [...r, r[0]] : r;
  const onMap = ([x, y]) => x >= 0 && y >= 0 && x <= W && y <= H;
  function onMapRuns(pts, closed) {
    const runs = []; let cur = [];
    for (const p of pts) { if (onMap(p)) cur.push(p); else { if (cur.length > 1) runs.push(cur); cur = []; } }
    if (cur.length > 1) runs.push(cur);
    if (closed && runs.length > 1 && onMap(pts[0]) && onMap(pts[pts.length - 1])) runs[0] = [...runs.pop(), ...runs[0]];   // wraps round
    return runs;
  }
  function drawWalls() {
    walls.children.forEach(o => { o.geometry.dispose(); if (o.userData.isPole) o.material.dispose(); }); walls.clear();
    labels.children.forEach(o => { o.material.map.dispose(); o.material.dispose(); }); labels.clear();
    wallMats.forEach(m => m.dispose()); wallMats.length = 0;
    lineMats.forEach(m => m.dispose()); lineMats.length = 0;
    for (const o of outlines) {
      const status = statusById[o.id] || "unknown", color = GLOW[status] ?? GLOW.unknown, focus = o.id === focusId;
      const all = densify(closeRing(o.ring)), hMul = (focus ? 1.6 : 1) * (status === "act" ? 1.3 : 1);
      const whole = all.every(onMap), runs = whole ? [all] : onMapRuns(all, true);
      o.offMap = !whole;
      const mat = new THREE.ShaderMaterial({vertexShader: WALL_VERT, fragmentShader: WALL_FRAG, transparent: true, depthWrite: false,
        side: THREE.DoubleSide, blending: THREE.AdditiveBlending,
        uniforms: {color: {value: new THREE.Color(color)}, time: {value: 0}, strength: {value: status === "act" ? 1.25 : 1}, uHeight: {value: 0.03}}});
      mat.userData.pulse = status === "act"; mat.userData.hMul = hMul;
      wallMats.push(mat);
      const lineMat = tubeMaterial(color, focus ? 1.6 : 1);
      for (const pts of runs) {
        const P = new Float32Array(pts.length * 6), V = new Float32Array(pts.length * 2), idx = [];
        pts.forEach(([x, y], k) => {
          const b = toScene(x, y, 0.0008);
          P.set([b.x, b.y, b.z, b.x, b.y, b.z], k * 6); V[k * 2] = 0; V[k * 2 + 1] = 1;   // top row is raised in the shader
          if (k < pts.length - 1) { const a = k * 2; idx.push(a, a + 2, a + 1, a + 1, a + 2, a + 3); }
        });
        const g = new THREE.BufferGeometry();
        g.setAttribute("position", new THREE.BufferAttribute(P, 3)); g.setAttribute("v", new THREE.BufferAttribute(V, 1)); g.setIndex(idx);
        const wall = new THREE.Mesh(g, mat); wall.renderOrder = 4; wall.userData.isWall = true; wall.visible = glowOn; walls.add(wall);
        // a solid bright line on the ground so the boundary reads from straight above too
        const path = straightPath(pts.map(([x, y]) => toScene(x, y, 0.001)), whole);
        if (!path.segments) continue;
        const line = new THREE.Mesh(new THREE.TubeGeometry(path.curve, path.segments, TUBE_R0, 5, false), lineMat);
        line.renderOrder = 5; walls.add(line);
      }
      {                                        // every pasture gets a flag; it's also the easiest thing to tap on a phone
        let [sx, sy] = interiorPoint(o.ring);
        if (!onMap([sx, sy])) [sx, sy] = interiorPoint(o.ring.map(([x, y]) => [Math.min(W, Math.max(0, x)), Math.min(H, Math.max(0, y))]));  // middle of the part on the map
        const sp = label((o.live && o.name) || namesById[o.id] || o.name, color); sp.position.copy(toScene(sx, sy, 0.002));
        sp.center.set(0.5, 0);                 // flag sits on top of its pole
        sp.userData.ground = sp.position.y; sp.userData.pasture = o.id;
        if (outlines.length > 25) sp.userData.k = 0.032;
        labels.add(sp);
        const pole = new THREE.Line(new THREE.BufferGeometry().setFromPoints([sp.position.clone(), sp.position.clone()]),
          new THREE.LineBasicMaterial({color: 0xffffff, transparent: true, opacity: 0.85, depthTest: false}));
        pole.renderOrder = 9; pole.userData.isPole = true; pole.userData.flag = sp; pole.visible = flagsOn; walls.add(pole);
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
  const toLocal = (lat, lon) => {               // metres from the map's SW corner, even off the map
    if (!zoneMatch || !origin) return null;
    const [ux, uy] = toUTM(lat, lon, +zoneMatch[2], zoneMatch[1] === "7");
    return [ux - origin[0], uy - origin[1]];
  };
  const localXY = (lat, lon) => {
    if (!zoneMatch || !origin) return null;
    const [ux, uy] = toUTM(lat, lon, +zoneMatch[2], zoneMatch[1] === "7");
    const x = ux - origin[0], y = uy - origin[1];
    return x >= 0 && y >= 0 && x <= W && y <= H ? [x, y] : null;
  };
  const pins = new THREE.Group(); scene.add(pins);
  const pinTex = {};
  // A white disc with the ranch icon (icons.js), ringed red when it needs attention; emoji if the icon isn't there.
  function pinTexture(flag, icon = "📷", ikey = null) {
    const url = ikey && window.RangeIcons && window.RangeIcons.url(ikey);
    const key = (flag ? "f" : "n") + (url ? "#" + ikey : icon);
    if (pinTex[key]) return pinTex[key];
    const c = document.createElement("canvas"); c.width = c.height = 128; const g = c.getContext("2d");
    g.fillStyle = "#ffffff"; g.strokeStyle = flag ? "#d63c2f" : "#1d2a44"; g.lineWidth = flag ? 10 : 7;
    g.beginPath(); g.arc(64, 64, 56, 0, Math.PI * 2); g.fill(); g.stroke();
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
    if (url) {
      const img = new Image();
      img.onload = () => { g.drawImage(img, 22, 22, 84, 84); t.needsUpdate = true; };
      img.src = url;
    } else {
      g.font = "60px system-ui, 'Apple Color Emoji', 'Segoe UI Emoji'"; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(icon, 64, 69);
    }
    return (pinTex[key] = t);
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
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({map: pinTexture(!!p.flagged, p.icon || "📷", p.ikey), depthTest: false}));
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

  // ---------------------------------------------------------------- you are here
  const hereObj = new THREE.Group(); hereObj.visible = false; scene.add(hereObj);
  const hereDot = new THREE.Mesh(new THREE.SphereGeometry(0.009, 20, 14), new THREE.MeshBasicMaterial({color: 0x2b7de9, fog: false, depthTest: false}));
  const hereRing = new THREE.Mesh(new THREE.RingGeometry(0.011, 0.016, 32), new THREE.MeshBasicMaterial({color: 0xffffff, fog: false, depthTest: false, side: THREE.DoubleSide}));
  hereRing.rotation.x = -Math.PI / 2;
  const hereArrow = new THREE.Mesh(new THREE.ConeGeometry(0.008, 0.022, 3), new THREE.MeshBasicMaterial({color: 0x2b7de9, fog: false, depthTest: false}));
  hereArrow.geometry.rotateX(-Math.PI / 2); hereArrow.geometry.translate(0, 0, -0.022);   // points north (-z) before turning
  // drawn in the see-through pass after labels and pins (renderOrder 30 > 12), so nothing covers it
  [hereDot, hereRing, hereArrow].forEach(m => { m.material.transparent = true; m.renderOrder = 30; hereObj.add(m); });

  // ---------------------------------------------------------------- roads, trails and other lines, draped on the ground
  const roads = new THREE.Group(); scene.add(roads);
  let lineList = [];
  function drawLines() {
    roads.children.forEach(o => o.geometry.dispose()); roads.clear();
    roadMats.forEach(m => m.dispose()); roadMats.length = 0;
    for (const ln of lineList) {
      const pts = ln.coords.map(([lon, lat]) => toLocal(lat, lon)).filter(Boolean);
      if (pts.length < 2) continue;
      const mat = tubeMaterial(ln.color, (ln.width || 3) / 4, roadMats);
      for (const run of onMapRuns(densify(pts), false)) {
        const path = straightPath(run.map(([x, y]) => toScene(x, y, 0.0012)), false);
        if (!path.segments) continue;
        const tube = new THREE.Mesh(new THREE.TubeGeometry(path.curve, path.segments, TUBE_R0, 6, false), mat);
        tube.renderOrder = 5; tube.userData.shape = ln.id; roads.add(tube);
      }
    }
  }

  // ---------------------------------------------------------------- tap: photo pin first, then pasture under the finger
  const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
  let down = null, picker = null, lastPastures = "";
  renderer.domElement.addEventListener("pointerdown", e => { down = [e.clientX, e.clientY]; });
  // Select on "click", not "pointerup". On a touchscreen the browser sends a click after the finger lifts, aimed at
  // whatever is on top by then; if the pasture sheet opened on pointerup, that click hit the sheet's backdrop and
  // closed it straight away. That's why tapping pastures worked with a mouse but not on phones.
  renderer.domElement.addEventListener("click", e => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 14) return;     // a finger tap moves a little
    const r = renderer.domElement.getBoundingClientRect();
    ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    if (picker) {                                  // "tap the map where it is"
      const g = ray.intersectObject(mesh)[0]; if (!g || !zoneMatch || !origin) return;
      const lx = g.point.x / S + W / 2, ly = H / 2 - g.point.z / S;
      const [lat, lon] = fromUTM(lx + origin[0], ly + origin[1], +zoneMatch[2], zoneMatch[1] === "7");
      const cb = picker; picker = null; renderer.domElement.style.cursor = ""; cb(lat, lon); return;
    }
    const hitPin = ray.intersectObjects(pins.children.filter(o => o.isSprite))[0];
    const hitFlag = !hitPin && labels.visible && ray.intersectObjects(labels.children)[0];
    if (hitFlag && hitFlag.object.userData.pasture) { onPasture(hitFlag.object.userData.pasture); return; }
    if (hitPin) { onPhoto(hitPin.object.userData.photo); return; }
    const hit = ray.intersectObject(mesh)[0]; if (!hit) return;
    const x = hit.point.x / S + W / 2, y = H / 2 - hit.point.z / S;
    for (const o of outlines) {
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
    const f = focusId && outlines.find(o => o.id === focusId);
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
    if (hereObj.visible) {                        // same size on screen at any zoom, with a gentle pulse
      const d = camera.position.distanceTo(hereObj.position), sz = Math.min(6, Math.max(0.08, d * 1.7));
      hereObj.scale.set(sz, sz, sz); const k = 1 + 0.25 * Math.sin(t * 4); hereRing.scale.set(k, k, k);
    }
    // screen-sized walls and lines: d is how far the camera is from what it looks at (about 1.2 for the whole ranch)
    const d = camera.position.distanceTo(controls.target);
    const wallH = Math.min(0.06, d * 0.03), closeFade = Math.min(1, Math.max(0.35, d / 0.4)), r = d * 0.0016;
    wallMats.forEach(m => { m.uniforms.uHeight.value = wallH * m.userData.hMul; });
    lineMats.forEach(m => { m.uniforms.uRadius.value = r * m.userData.widthMul; });
    roadMats.forEach(m => { m.uniforms.uRadius.value = r * 0.8 * m.userData.widthMul; });
    for (const sp of labels.children) sp.position.y = sp.userData.ground + wallH + d * 0.03;
    for (const pole of walls.children) if (pole.userData.isPole) {          // flag pole from the ground up to the flag
      const p = pole.geometry.attributes.position, sp = pole.userData.flag;
      p.setXYZ(0, sp.position.x, sp.userData.ground, sp.position.z); p.setXYZ(1, sp.position.x, sp.position.y, sp.position.z); p.needsUpdate = true;
    }
    wallMats.forEach(m => { m.uniforms.time.value = t; if (m.userData.pulse) m.uniforms.strength.value = 1.15 + 0.25 * Math.sin(t * 3); });
    wallMats.forEach(m => { if (!m.userData.pulse) m.uniforms.strength.value = closeFade; else m.uniforms.strength.value *= closeFade; });
    for (const sp of [...labels.children, ...pins.children.filter(o => o.isSprite)]) {
      const d = camera.position.distanceTo(sp.position), k = sp.userData.k; sp.scale.set(k * d * sp.userData.aspect, k * d, 1);
    }
    renderer.render(scene, camera);
    requestAnimationFrame(loop);
  })();

  return {
    setExaggeration(v) {                        // the slider sends many values; redraw once per frame
      exag = v; if (exagPending) return; exagPending = true;
      requestAnimationFrame(() => { exagPending = false; applyHeights(); drawWalls(); drawPins(); drawLines();
        if (hereObj.userData.xy) hereObj.position.copy(toScene(hereObj.userData.xy[0], hereObj.userData.xy[1], 0.004)); });
    },
    setLook,
    setPhotos(list) { photoList = list || []; drawPins(); },
    setLines(list) { lineList = list || []; drawLines(); },
    setFlags(on) {                                // pasture flags on/off (Layers); tapping the ground still opens a pasture
      flagsOn = on !== false; labels.visible = flagsOn && walls.visible;
      walls.children.forEach(o => { if (o.userData.isPole) o.visible = flagsOn; });
    },
    setGlow(on) { glowOn = !!on; walls.children.forEach(o => { if (o.userData.isWall) o.visible = glowOn; }); },
    setHere(h) {                                   // the phone's GPS position: a blue dot on the ground
      hereObj.visible = false; if (!h) return;
      const xy = localXY(h.lat, h.lon); if (!xy) return;
      hereObj.position.copy(toScene(xy[0], xy[1], 0.004)); hereObj.visible = true; hereObj.userData.xy = xy;
      hereArrow.visible = h.heading != null; if (h.heading != null) hereArrow.rotation.y = -h.heading * D2R;
    },
    setStatuses(map) { statusById = map || {}; drawWalls(); },
    setPastures(list) {                           // [{id, name, coords: [[lon, lat], ...]}], the boundaries as they are now
      if (!zoneMatch || !origin || !list || !list.length) return;
      const next = list.map(p => ({id: p.id, name: p.name, live: true, ring: p.coords.map(([lon, lat]) => toLocal(lat, lon))}))
        .filter(o => o.ring.length >= 3 && o.ring.every(Boolean));
      const key = JSON.stringify(next);
      if (!next.length || key === lastPastures) return;
      lastPastures = key; outlines = next; drawWalls();
    },
    offMap() { return outlines.filter(o => o.offMap).map(o => o.name); },   // pastures reaching past the 3D map's edge
    setPasturesVisible(on) { walls.visible = !!on; labels.visible = !!on && flagsOn; },
    pickOnce(cb) { picker = cb; renderer.domElement.style.cursor = "crosshair"; },
    cancelPick() { picker = null; renderer.domElement.style.cursor = ""; },
    flagPositions() {                              // where each pasture flag is on screen (used by the browser tests)
      const r = renderer.domElement.getBoundingClientRect();
      return labels.children.map(sp => { const v = sp.position.clone().project(camera);
        return {id: sp.userData.pasture, x: r.left + (v.x + 1) / 2 * r.width, y: r.top + (1 - v.y) / 2 * r.height}; });
    },
    focus(lat, lon) {                              // fly to a GPS point
      const xy = localXY(lat, lon); if (!xy) return false;
      const target = toScene(xy[0], xy[1]);
      controls.target.copy(target);
      camera.position.copy(target).addScaledVector(new THREE.Vector3(-0.3, 0.62, 0.72).normalize(), 0.16);
      controls.update(); return true;
    },
    reset,
    dispose() {
      running = false; ro.disconnect(); controls.dispose();
      walls.children.forEach(o => o.geometry.dispose()); wallMats.forEach(m => m.dispose()); lineMats.forEach(m => m.dispose()); roadMats.forEach(m => m.dispose());
      geo.dispose(); photoTex.dispose(); photoMat.dispose(); if (topoMat) { topoMat.map.dispose(); topoMat.dispose(); }
      Object.values(pinTex).forEach(t => t.dispose()); renderer.dispose(); container.innerHTML = "";
    }
  };
}
