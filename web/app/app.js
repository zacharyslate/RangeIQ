/* RangeIQ phone app (ranch-hand edition). Plain JavaScript, no build step.
   Server (rangeiq.org) does the processing; the app shows results, takes photos and logs work.
   Everything a hand records is saved on the phone first and sent when there's signal. */
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const API = new URL(window.RANGEIQ_API || "../api/", location.href).href;
  const store = {
    get(k, d) { try { const v = localStorage.getItem("riq." + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem("riq." + k, JSON.stringify(v)); } catch (e) {} },
    del(k) { try { localStorage.removeItem("riq." + k); } catch (e) {} }
  };
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const STATUS = {good: {word: "Good", icon: "✓"}, watch: {word: "Watch", icon: "!"}, act: {word: "Act", icon: "!!"}, unknown: {word: "No data", icon: "?"}};
  const LEVEL = {ok: "✓", watch: "!", concern: "!!", unavailable: "–"};
  // What a hand can tap: [tag, level, map icon]. Keep in step with TAG_LEVELS in src/ranch_ai/rancher/status.py (a test checks).
  // concern = serious (pasture Act); watch = something off; alert = heads-up for people; info = sighting; good = fine.
  const TAG_GROUPS = /*TAGS*/[
    {"group": "Water", "icon": "💧", "tags": [["Water low", "concern", "💧"], ["Trough or tank problem", "concern", "💧"], ["Windmill or pump down", "concern", "💧"],
      ["Pipe or float leak", "watch", "💧"], ["Water OK", "good", "💧"]]},
    {"group": "Fences, gates & roads", "icon": "🚧", "tags": [["Fence down", "concern", "🚧"], ["Fence damaged", "watch", "🚧"], ["Gate open", "watch", "🚪"],
      ["Gate damaged", "watch", "🚪"], ["Cattle guard problem", "watch", "🚧"], ["Washed-out road", "watch", "🛣️"]]},
    {"group": "Livestock", "icon": "🐄", "tags": [["Cattle out", "concern", "🐄"], ["Sick or hurt animal", "concern", "🐄"], ["Dead animal", "concern", "🐄"],
      ["Stray animal", "watch", "🐄"], ["New calf", "info", "🐮"]]},
    {"group": "Wildlife", "icon": "🦌", "tags": [["Feral hogs", "watch", "🐗"], ["Hog rooting damage", "watch", "🐗"], ["Coyote or predator", "watch", "🐺"],
      ["Rattlesnake", "alert", "🐍"], ["Deer", "info", "🦌"], ["Other wildlife", "info", "🐾"]]},
    {"group": "Grass & land", "icon": "🌾", "tags": [["Fire or smoke", "concern", "🔥"], ["Short or overgrazed grass", "watch", "🌾"], ["Weeds or brush", "watch", "🌿"],
      ["Poisonous plants", "watch", "☠️"], ["Erosion or washout", "watch", "🌊"], ["Good grass", "good", "🌾"]]}
  ]/*END*/;
  const TAG = {};
  TAG_GROUPS.forEach(g => g.tags.forEach(([name, level, icon]) => { TAG[name] = {level, icon, group: g.group}; }));
  const tagsAt = (tags, levels) => (tags || []).filter(t => TAG[t] && levels.includes(TAG[t].level));
  const PROBLEM_TAGS = Object.keys(TAG).filter(t => ["concern", "watch"].includes(TAG[t].level));
  const GOOD_TAGS = Object.keys(TAG).filter(t => TAG[t].level === "good");
  const HEADS_UP = ["concern", "watch", "alert"];
  const RANK = {concern: 4, alert: 3, watch: 2, info: 1, good: 0};
  const topTag = tags => (tags || []).filter(t => TAG[t]).sort((a, b) => RANK[TAG[b].level] - RANK[TAG[a].level])[0];
  const tagClass = t => !TAG[t] ? "" : TAG[t].level === "good" ? " ok" : ["info", "alert"].includes(TAG[t].level) ? " info" : "";
  const tagSpan = t => `<span class="tag${tagClass(t)}">${TAG[t] ? TAG[t].icon + " " : ""}${esc(t)}</span>`;
  const COLOR = {good: "#2e9d55", watch: "#e0a21b", act: "#d63c2f", unknown: "#8a8f96"};

  // Drought and rain are the same for every pasture and are "pretty normal out there", so the crew can switch them off.
  // Then a pasture's status comes from its own evidence: greenness, long-term trend, grazing days and crew reports.
  const EVERYDAY = ["drought", "rain"];
  function combineSignals(signals) {            // same rules as status.combine() on the server
    const usable = signals.filter(g => g.level !== "unavailable");
    if (!usable.length) return {status: "unknown", headline: "Not enough data yet to judge this pasture."};
    const field = usable.filter(g => g.level === "concern" && g.key === "field");
    const concerns = [...field, ...usable.filter(g => g.level === "concern" && g.key !== "field")], watches = usable.filter(g => g.level === "watch");
    const status = concerns.length >= 2 || field.length || (concerns.length && watches.length) ? "act" : concerns.length || watches.length ? "watch" : "good";
    const lead = (concerns[0] || watches[0] || usable[0]);
    return {status, headline: status === "act" ? "Act: " + lead.text : status === "watch" ? "Watch: " + lead.text
      : "Looks good. " + (["grass", "rain"].includes(lead.key) ? lead.text : "No warning signs in the data.")};
  }
  function viewOf(raw) {
    if (!raw || !raw.pastures || !store.get("hideEveryday", false)) return raw;
    return {...raw, pastures: raw.pastures.map(p => ({...p, ...combineSignals((p.signals || []).filter(g => !EVERYDAY.includes(g.key))),
      signals: p.signals}))};
  }
  let rawSnap = store.get("snapshot", null), snap = viewOf(rawSnap), snapAt = store.get("snapshotAt", null);
  function setHideEveryday(on) { store.set("hideEveryday", !!on); snap = viewOf(rawSnap); if (view3d) view3d.setStatuses(statusMap()); rerender(); }
  let me = store.get("me", null);
  let photos = store.get("photos", []), serverLogs = store.get("serverLogs", []);
  let pending = [];                      // photos waiting to upload (from IndexedDB), with object URLs
  let currentPasture = null, photoHere = null;
  let map = null, mapLayers = [], view3d = null;
  let mapMode = "3d", look = store.get("look", "photo"), exag = 2, logFilter = "all";   // the map always opens in 3D

  // ---------------------------------------------------------------- small helpers
  const uid = () => (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2)).replace(/[^A-Za-z0-9-]/g, "").slice(0, 36);
  function when(iso, withTime = true) {
    if (!iso) return "";
    if (/^\d{4}$/.test(String(iso))) return String(iso);
    const d = new Date(String(iso).length === 10 ? iso + "T12:00:00" : iso); if (isNaN(d)) return iso;
    const mins = (Date.now() - d) / 6e4;
    if (withTime && mins >= 0 && mins < 1) return "just now";
    if (withTime && mins >= 0 && mins < 60) return Math.round(mins) + " min ago";
    const today = new Date(), yday = new Date(Date.now() - 864e5), same = (a, b) => a.toDateString() === b.toDateString();
    const t = d.toLocaleTimeString([], {hour: "numeric", minute: "2-digit"});
    if (same(d, today)) return withTime ? "today " + t : "today";
    if (same(d, yday)) return withTime ? "yesterday " + t : "yesterday";
    return d.toLocaleDateString([], {month: "short", day: "numeric", year: d.getFullYear() === today.getFullYear() ? undefined : "numeric"}) + (withTime ? " " + t : "");
  }
  function toast(msg) { const t = document.createElement("div"); t.className = "toast"; t.textContent = msg; document.body.appendChild(t); setTimeout(() => t.remove(), 2800); }
  const compass = h => h == null ? "" : ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][Math.round(((h % 360) + 360) % 360 / 45) % 8];
  function metres(a, b) {
    const R = 6371000, r = Math.PI / 180, dLat = (b.lat - a.lat) * r, dLon = (b.lon - a.lon) * r;
    const x = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(x));
  }
  function pastureAt(lon, lat) {
    for (const p of (snap && snap.pastures) || []) {
      let inside = false; const ring = p.outline;
      for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const [xi, yi] = ring[i], [xj, yj] = ring[j];
        if ((yi > lat) !== (yj > lat) && lon < (xj - xi) * (lat - yi) / (yj - yi) + xi) inside = !inside;
      }
      if (inside) return p.id;
    }
    return null;
  }
  const pastureName = id => { const p = ((snap && snap.pastures) || []).find(x => x.id === id); return p ? p.name : (id || ""); };
  const isOwner = () => !me || me.role !== "crew";

  // ---------------------------------------------------------------- API
  function authHeaders(extra = {}) { const t = store.get("token", null); return t ? {...extra, Authorization: "Bearer " + t} : extra; }
  async function api(path, opts = {}) {
    const headers = opts.body instanceof FormData ? authHeaders(opts.headers || {}) : authHeaders({"Content-Type": "application/json", ...(opts.headers || {})});
    const res = await fetch(API + path, {credentials: "same-origin", ...opts, headers});
    if (res.status === 401 && !["login", "join"].includes(path)) { store.del("token"); const e = new Error("signin"); e.signin = true; throw e; }
    if (!res.ok) { const e = new Error((await res.json().catch(() => ({}))).detail || ("HTTP " + res.status)); e.status = res.status; throw e; }
    return res.json();
  }
  async function getBytes(path) {
    const res = await fetch(API + path, {credentials: "same-origin", headers: authHeaders()});
    if (res.status === 401) { const e = new Error("signin"); e.signin = true; throw e; }
    if (!res.ok) throw new Error(res.status === 404 ? "notready" : "HTTP " + res.status);
    return {bytes: await res.arrayBuffer(), mime: res.headers.get("Content-Type") || ""};
  }
  const fileUrl = rel => new URL(rel, API).href;

  // ---------------------------------------------------------------- photo queue (IndexedDB: photos are too big for localStorage)
  const idb = {
    db: null,
    open() {
      if (this.db) return Promise.resolve(this.db);
      return new Promise((ok, fail) => {
        const r = indexedDB.open("rangeiq", 1);
        r.onupgradeneeded = () => r.result.createObjectStore("photos", {keyPath: "client_id"});
        r.onsuccess = () => { this.db = r.result; ok(this.db); };
        r.onerror = () => fail(r.error);
      });
    },
    async run(mode, fn) {
      const db = await this.open();
      return new Promise((ok, fail) => { const t = db.transaction("photos", mode); const req = fn(t.objectStore("photos")); t.oncomplete = () => ok(req && req.result); t.onerror = () => fail(t.error); });
    },
    put(rec) { return this.run("readwrite", s => s.put(rec)); },
    del(id) { return this.run("readwrite", s => s.delete(id)); },
    all() { return this.run("readonly", s => s.getAll()); }
  };
  async function loadPending() {
    pending.forEach(p => { URL.revokeObjectURL(p.thumbUrl); URL.revokeObjectURL(p.imageUrl); });
    try { pending = (await idb.all() || []).map(r => ({...r.meta, client_id: r.client_id, _pending: true,
      thumbUrl: URL.createObjectURL(r.thumb), imageUrl: URL.createObjectURL(r.photo)})); } catch (e) { pending = []; }
  }
  const allPhotos = () => [...pending, ...photos.filter(p => !pending.some(q => q.client_id === p.client_id))]
    .sort((a, b) => String(b.taken_at).localeCompare(String(a.taken_at)));
  // Photos from the same spot (a "photo point") share one pin; the photo sheet shows that spot over time.
  const SPOT_M = 15;
  function spots(list) {
    const out = [];
    for (const p of list) {                    // newest first
      if (p.lat == null) continue;
      const s = out.find(x => metres(x, p) <= SPOT_M);
      if (s) s.n++; else out.push({lat: p.lat, lon: p.lon, heading_deg: p.heading_deg, flagged: p.flagged, client_id: p.client_id, taken_at: p.taken_at, n: 1});
    }
    return out;
  }
  // ---------------------------------------------------------------- map layers: everything on the ranch, switchable
  const PLACE_KINDS = {
    water_tank: ["Water tank", "🛢️", "water"], trough: ["Trough", "💧", "water"], pond: ["Pond / dirt tank", "🌊", "water"],
    windmill: ["Windmill / well", "🌀", "water"], water_other: ["Other water", "💧", "water"],
    deer_blind: ["Deer blind", "🛖", "hunting"], feeder: ["Feeder", "🌽", "hunting"], game_camera: ["Game camera", "📸", "hunting"],
    stand: ["Stand", "🪜", "hunting"],
    gate: ["Gate", "🚪", "ranch"], cattle_guard: ["Cattle guard", "🚧", "ranch"], pens: ["Pens / corral", "🐂", "ranch"],
    building: ["Building / barn", "🏠", "ranch"], mineral: ["Mineral / salt", "🧂", "ranch"], other: ["Other", "📍", "ranch"],
    sensor_rain: ["Rain gauge sensor", "📡", "sensors"], sensor_water: ["Water-level sensor", "📡", "sensors"],
    sensor_soil: ["Soil moisture sensor", "📡", "sensors"], sensor_weather: ["Weather station", "📡", "sensors"], sensor_other: ["Other sensor", "📡", "sensors"]};
  const LAYERS = [["pastures", "Pastures", "🟫"], ["colors", "Warning colors", "🚦"], ["water", "Water", "💧"], ["hunting", "Hunting", "🛖"],
    ["ranch", "Ranch places", "🏠"], ["usgs", "USGS water map", "🗺️"], ["sensors", "Sensors", "📡"], ["wildlife", "Wildlife & sightings", "🦌"], ["problems", "Problems", "⚠️"], ["photos", "Other photos", "📷"],
    ["jobs", "Jobs", "✅"]];
  let layers = {...Object.fromEntries(LAYERS.map(([k]) => [k, true])), ...store.get("layers", {})};
  let places = store.get("places", []);
  function layerOfTags(tags) {
    if (tagsAt(tags, HEADS_UP).length) return "problems";
    if ((tags || []).some(t => TAG[t] && (TAG[t].group === "Wildlife" || TAG[t].level === "info"))) return "wildlife";
    return null;
  }
  function mapItems() {                         // every pin, with the layer it belongs to
    const out = [];
    const loose = allPhotos().filter(p => !p.place_id);
    for (const sp of spots(loose)) {
      const newest = loose.find(p => p.client_id === sp.client_id) || {};
      const lay = layerOfTags(newest.tags) || "photos", top = topTag(newest.tags);
      out.push({...sp, layer: lay, icon: lay === "photos" ? "📷" : (top ? TAG[top].icon : "📷"), title: (newest.tags || []).join(", ") || "Photo"});
    }
    logItems().filter(i => i.type === "problem" && i.l.lat != null).forEach(i => {
      const top = topTag(i.l.tags);
      out.push({client_id: i.l.client_id, lat: i.l.lat, lon: i.l.lon, icon: top ? TAG[top].icon : "📝", taken_at: i.at, report: true,
        layer: layerOfTags(i.l.tags) || "problems", flagged: tagsAt(i.l.tags, HEADS_UP).length > 0, title: (i.l.tags || []).join(", ") || i.l.text || "Report"});
    });
    places.forEach(pl => { const k = PLACE_KINDS[pl.kind] || PLACE_KINDS.other;
      out.push({client_id: pl.place_id, lat: pl.lat, lon: pl.lon, icon: k[1], layer: k[2], place: true, title: pl.name}); });
    const USGS_ICON = {tank: "💧", pond: "🌊", playa: "🏜️", marsh: "🌾", spring: "💦", well: "🚰", dam: "🧱"};
    (((snap && snap.water_map) || {}).features || []).forEach(w =>
      out.push({client_id: w.id, lat: w.lat, lon: w.lon, icon: USGS_ICON[w.kind] || "💧", layer: "usgs", usgs: true, title: w.name || w.label}));
    tasks.filter(t => !t.done_at && t.lat != null).forEach(t =>
      out.push({client_id: t.task_id, lat: t.lat, lon: t.lon, icon: "✅", layer: "jobs", task: true, title: t.title, flagged: taskBucket(t) === "late"}));
    return out.filter(x => layers[x.layer]);
  }
  function openWater(id) {
    const w = (((snap && snap.water_map) || {}).features || []).find(x => x.id === id); if (!w) return;
    const kind = {tank: "water_tank", pond: "pond", playa: "pond", marsh: "water_other", spring: "water_other", well: "windmill", dam: "pond"}[w.kind] || "water_other";
    openSheet(w.name || w.label, `<p><b>${esc(w.label)}</b>${w.acres ? ` · ${w.acres < 1 ? w.acres.toFixed(2) : w.acres.toFixed(1)} acres` : ""}${w.intermittent ? " · holds water only part of the year" : ""}</p>
      <p class="dim small">From the USGS National Hydrography Dataset (${esc(((snap.water_map || {}).as_of) || "")}). It was mapped from older aerial photos, so some tanks are missing, moved or dry. Save the real ones as your own places.</p>
      <div class="row"><button type="button" class="primary" id="wSave">Save as our place</button><button type="button" class="secondary" id="wMap">Show on map</button></div>`);
    $("wSave").onclick = () => addPlace({kind, name: w.name || PLACE_KINDS[kind][0], lat: w.lat, lon: w.lon});
    $("wMap").onclick = () => showOnMap(w.lat, w.lon);
  }
  function openItem(id) {
    if (String(id).startsWith("nhd-")) return openWater(id);
    if (places.some(p => p.place_id === id)) return openPlace(id);
    if (tasks.some(t => t.task_id === id)) return openTask(id);
    return openPhoto(id);
  }
  function statusMap() {
    const m = {}; ((snap && snap.pastures) || []).forEach(p => { m[p.id] = layers.colors ? p.status : "unknown"; }); return m;
  }
  function showOnMap(lat, lon) {
    closeSheet(); show("map");
    const go = () => { if (view3d && view3d.focus(lat, lon)) return; mapMode = "2d"; renderMap().then(() => map && map.setView([lat, lon], 17)); };
    setTimeout(go, view3d ? 50 : 1500);
  }
  const sameSpot = p => p.lat == null ? [p] : allPhotos().filter(x => x.lat != null && metres(x, p) <= 35);
  const thumbOf = p => p._pending ? p.thumbUrl : fileUrl(p.thumb_url);
  const imageOf = p => p._pending ? p.imageUrl : fileUrl(p.image_url);

  // ---------------------------------------------------------------- views
  const TABS = ["home", "todo", "map", "log", "more"];
  const OLD = {today: "home", pastures: "map", terrain: "map"};
  function show(view) {
    view = OLD[view] || view || "home";
    if (view.startsWith("act-")) { setTimeout(() => act(view.slice(4)), 80); view = "home"; }
    if (view.startsWith("log-")) { setTimeout(() => act(view.slice(4)), 80); view = "home"; }
    let tab = view;
    if (view.startsWith("pasture-")) { currentPasture = decodeURIComponent(view.slice(8)); tab = "pasture"; }
    if (!["login", "pasture", ...TABS].includes(tab)) tab = "home";
    if (tab !== "map" && view3d) { view3d.dispose(); view3d = null; }
    document.querySelectorAll(".view").forEach(v => { v.hidden = v.id !== "v-" + tab; });
    document.querySelectorAll(".tabs [data-tab]").forEach(b => {
      const on = b.dataset.tab === (tab === "pasture" ? "map" : tab);
      if (on) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
    });
    document.querySelector(".tabs").hidden = tab === "login";
    const hash = tab === "pasture" ? "pasture-" + encodeURIComponent(currentPasture) : tab;
    if (location.hash !== "#" + hash) history.replaceState(null, "", "#" + hash);
    ({home: renderHome, todo: renderTodo, map: renderMap, pasture: renderPasture, log: renderLog, more: renderMore}[tab] || (() => {}))();
    window.scrollTo(0, 0);
  }
  document.querySelectorAll(".tabs [data-tab]").forEach(b => b.onclick = () => { if (b.dataset.tab === "map") mapMode = "3d"; show(b.dataset.tab); });
  document.addEventListener("click", e => {
    const go = e.target.closest("[data-go]"); if (go) { show(go.dataset.go); return; }
    const p = e.target.closest("[data-pasture]"); if (p) { show("pasture-" + encodeURIComponent(p.dataset.pasture)); return; }
    const ph = e.target.closest("[data-photo]"); if (ph) { openPhoto(ph.dataset.photo); return; }
    const a = e.target.closest("[data-act]"); if (a) act(a.dataset.act, a.dataset.here ? currentPasture : null);
  });
  window.addEventListener("hashchange", () => show(location.hash.slice(1)));

  function setBanner() {
    const b = $("banner"), parts = [];
    if (snap && snap.demo) parts.push("Demo data: these numbers are examples, not your ranch.");
    if (!navigator.onLine) parts.push("No signal. Showing what was saved " + (snapAt ? when(snapAt) : "earlier") + ". Photos and logs will send later.");
    b.hidden = !parts.length; b.textContent = parts.join(" "); b.classList.toggle("demo", !!(snap && snap.demo) && navigator.onLine);
  }
  window.addEventListener("online", () => { setBanner(); refresh(); syncAll(); });
  window.addEventListener("offline", setBanner);

  // ---------------------------------------------------------------- data
  async function refresh() {
    try {
      const data = await api("snapshot");
      if (data.pending || data.setup_needed) { rawSnap = snap = null; store.del("snapshot"); store.set("setupMsg", data.message); }
      else { rawSnap = data; snap = viewOf(data); snapAt = new Date().toISOString(); store.set("snapshot", data); store.set("snapshotAt", snapAt); store.del("setupMsg"); }
      const [m, ph, lg] = await Promise.all([api("me"), api("photos").catch(() => photos), api("logs").catch(() => serverLogs), loadTasks(), loadPlaces()]);
      me = m; photos = ph; serverLogs = lg; if (m.workspace_id) store.set("lastRanch", m.workspace_id);
      store.set("me", me); store.set("photos", photos); store.set("serverLogs", serverLogs);
    } catch (e) {
      if (e.signin) { show("login"); return; }
    } finally { setBanner(); rerender(); }
  }
  function rerender() {
    const v = [...document.querySelectorAll(".view")].find(x => !x.hidden);
    if (!v) return;
    ({"v-home": renderHome, "v-todo": renderTodo, "v-pasture": renderPasture, "v-log": renderLog, "v-more": renderMore}[v.id] || (() => {}))();
    if (v.id === "v-map" && mapMode === "2d") renderMap();
    updateSyncPill();
  }

  // ---------------------------------------------------------------- HOME
  function renderHome() {
    $("brandName").textContent = (snap && snap.ranch.name) || (me && me.ranch) || "RangeIQ";
    $("brandCaret").hidden = !(me && (me.ranches || []).length > 1);
    $("h-h").textContent = (snap && snap.ranch.name) || "Today";
    $("h-updated").textContent = snap ? "Updated " + when(snap.generated_at) : "";
    homeTodo();
    const box = $("h-attention");
    if (!snap) {
      box.innerHTML = `<h2>Getting started</h2><p class="dim">${esc(store.get("setupMsg", "") || "Waiting for the first ranch update…")}</p>`;
      $("h-weather").hidden = true; return;
    }
    const items = [];
    (snap.alerts || []).forEach(a => items.push({cls: "alert", lead: "⚡", title: a.event, why: a.what_it_means || a.headline}));
    if (snap.fire && !/low/i.test(snap.fire.level)) items.push({cls: "watch", lead: "🔥", title: "Fire danger: " + snap.fire.level, why: (snap.fire.drivers || []).join(" · ")});
    const cutoff = Date.now() - 3 * 864e5;
    // What the crew saw in the last 3 days (photos and reports), before the server's next update folds it into pasture status.
    // Sightings (deer, new calf) stay in the Log and on the map; only problems and heads-ups (rattlesnake) come here.
    logItems().filter(i => (i.type === "photo" || i.type === "problem") && new Date(i.at) > cutoff)
      .map(i => ({i, x: i.p || i.l, hot: tagsAt((i.p || i.l).tags, HEADS_UP)}))
      .filter(({i, x, hot}) => hot.length || (i.p && x.flagged))
      .sort((a, b) => (RANK[TAG[topTag(b.hot)]?.level] || 0) - (RANK[TAG[topTag(a.hot)]?.level] || 0)).slice(0, 4)
      .forEach(({i, x, hot}) => { const top = topTag(hot); items.push({
        cls: top && TAG[top].level === "concern" ? "act" : "watch", lead: top ? TAG[top].icon : "📷",
        title: hot.join(", ") || "Much less green than before",
        why: `${x.pasture_id ? pastureName(x.pasture_id) + " · " : ""}${x.by ? x.by + " · " : ""}${when(i.at)}${x.text ? " · " + x.text : ""}${i.p ? " · 📷" : ""}`,
        photo: x.client_id}); });
    // Pastures: worst first; pastures with the same reason are grouped so the list stays short.
    const groups = new Map();
    snap.pastures.filter(p => p.status === "act" || p.status === "watch")
      .sort((a, b) => (a.status === "act" ? 0 : 1) - (b.status === "act" ? 0 : 1))
      .forEach(p => { const why = p.headline.replace(/^(Act|Watch):\s*/, ""), k = p.status + "|" + why;
        if (!groups.has(k)) groups.set(k, {status: p.status, why, list: []}); groups.get(k).list.push(p); });
    for (const g of groups.values()) {
      if (g.list.length === 1) items.push({cls: g.status, lead: STATUS[g.status].icon, title: g.list[0].name, why: g.why, pasture: g.list[0].id});
      else items.push({cls: g.status, lead: STATUS[g.status].icon, title: `${g.list.length === snap.pastures.length ? "All" : g.list.length} pastures: ${STATUS[g.status].word}`,
        why: `${g.why} (${g.list.map(p => p.name).join(", ")})`, go: "map"});
    }
    if (!items.length) {
      box.innerHTML = `<div class="allclear"><span class="big-ok" aria-hidden="true">✓</span><span>All clear. Nothing needs attention.</span></div>`;
    } else {
      box.innerHTML = `<h2>Needs attention</h2><ul class="attn">${items.slice(0, 7).map(i => `<li><button type="button" class="${i.cls}"
        ${i.pasture ? `data-pasture="${esc(i.pasture)}"` : i.photo ? `data-photo="${esc(i.photo)}"` : `data-go="${i.go || "map"}"`}>
        <span class="lead" aria-hidden="true">${i.lead}</span><b>${esc(i.title)}</b><span class="go" aria-hidden="true">›</span>
        <span class="why">${esc(i.why || "")}</span></button></li>`).join("")}</ul>`;
    }
    if (store.get("hideEveryday", false)) {
      const sig = ((rawSnap && rawSnap.pastures && rawSnap.pastures[0] && rawSnap.pastures[0].signals) || []).filter(g => EVERYDAY.includes(g.key) && g.level !== "ok" && g.level !== "unavailable");
      if (sig.length) box.insertAdjacentHTML("beforeend", `<p class="dim small">Not counted in pasture status (same for the whole ranch): ${sig.map(g => esc(g.text)).join(" ")}
        <button type="button" class="linkbtn" id="showEveryday">Count them again</button></p>`);
      if ($("showEveryday")) $("showEveryday").onclick = () => setHideEveryday(false);
    }
    renderSky();
    const w = snap.weather, r = snap.rain, wx = $("h-weather"); wx.hidden = false;
    if (!w) { wx.innerHTML = "<h2>Weather</h2><p class='dim'>Forecast not available right now.</p>"; return; }
    const today = (w.forecast || [])[0] || {};
    const pct = r && r.normal_90d_in ? Math.round(100 * r.rain_90d_in / r.normal_90d_in) : null;
    const day = d => new Date(d + "T12:00:00").toLocaleDateString([], {weekday: "short"});
    let tzw = snap.ranch && snap.ranch.timezone; try { new Intl.DateTimeFormat([], {timeZone: tzw}); } catch (e) { tzw = undefined; }
    const sunT = window.RangeSky && snap.ranch && snap.ranch.center ? window.RangeSky.sunTimes(new Date(), snap.ranch.center[1], snap.ranch.center[0]) : null;
    const isNight = sunT && sunT.sunrise && sunT.sunset ? (Date.now() < sunT.sunrise || Date.now() > sunT.sunset)
      : (h => h < 7 || h >= 20)(Number(new Intl.DateTimeFormat("en-US", {hour: "numeric", hour12: false, timeZone: tzw}).format(new Date())));
    wx.innerHTML = `<h2>Weather</h2><div class="wx"><span class="wxic" aria-hidden="true">${wxIcon(w.label, isNight)}</span><span class="now">${w.temp_f ?? "–"}°</span><span><b>${esc(w.label || "")}</b><br>
        <span class="dim">Wind ${w.wind_mph ?? "–"} mph${w.gust_mph ? ", gusts " + w.gust_mph : ""} · Rain ${today.rain_chance_pct ?? "–"}%</span></span></div>
      <div class="wx7" role="list" aria-label="Next 7 days">${(w.forecast || []).map((d, i) => `<div role="listitem" title="${esc(d.label || "")}"><span>${i === 0 ? "Today" : esc(day(d.date))}</span>
        <span class="wxic sm" aria-label="${esc(d.label || "")}">${wxIcon(d.label, false)}</span><b>${d.high_f ?? "–"}°</b><span class="dim">${d.low_f ?? "–"}°</span><span class="rain${(d.rain_chance_pct || 0) >= 50 ? " wet" : ""}">💧${d.rain_chance_pct ?? "–"}%</span>
        <span class="dim small">${d.gust_mph ? "💨" + d.gust_mph : d.wind_mph ? "💨" + d.wind_mph : ""}</span></div>`).join("")}</div>
      ${pct != null ? `<p class="dim">Rain last 90 days: <b>${r.rain_90d_in.toFixed(1)} in</b>, ${pct}% of normal.</p>` : ""}`;
  }

  // Weather picture from the forecast words (NWS / Open-Meteo labels)
  function wxIcon(label, night) {
    const l = String(label || "").toLowerCase();
    if (/thunder|t-storm|tstorm/.test(l)) return "⛈️";
    if (/snow|sleet|flurr|ice|freez/.test(l)) return "🌨️";
    if (/rain|shower|drizzle/.test(l)) return /chance|slight|isolated|scattered/.test(l) ? "🌦️" : "🌧️";
    if (/fog|haze|smoke|dust/.test(l)) return "🌫️";
    if (/wind|breez|blustery/.test(l)) return "💨";
    if (/overcast|^cloudy|mostly cloudy/.test(l)) return "☁️";
    if (/mostly clear|few clouds/.test(l)) return night ? "🌙" : "🌤️";
    if (/partly|mostly sunny/.test(l)) return night ? "☁️" : "⛅";
    if (/sun|clear|fair/.test(l)) return night ? "🌙" : "☀️";
    return "🌡️";
  }

  // ---------------------------------------------------------------- SKY: sun and moon for the ranch (worked out on the phone)
  function renderSky() {
    const box = $("h-sky"), c = snap && snap.ranch && snap.ranch.center;
    if (!c || !window.RangeSky) { box.hidden = true; return; }
    const [lon, lat] = c, S = window.RangeSky, now = new Date();
    let tz = snap.ranch.timezone || undefined;
    try { new Intl.DateTimeFormat([], {timeZone: tz}); } catch (e) { tz = undefined; }
    const t = d => d ? d.toLocaleTimeString([], {hour: "numeric", minute: "2-digit", timeZone: tz}) : "—";
    const parts = Object.fromEntries(new Intl.DateTimeFormat("en-US", {timeZone: tz, hour12: false, hour: "numeric", minute: "numeric", second: "numeric"})
      .formatToParts(now).map(p => [p.type, Number(p.value)]));
    const midnight = new Date(now - (((parts.hour % 24) * 60 + parts.minute) * 60 + parts.second) * 1000);
    const sun = S.sunTimes(new Date(midnight.valueOf() + 12 * 36e5), lat, lon), moon = S.moonTimes(midnight, lat, lon);
    const ill = S.moonIllumination(now), ph = S.phaseName(ill.phase);
    const full = S.nextPhase(now, 0.5), nw = S.nextPhase(now, 0);
    const dateOf = d => d ? d.toLocaleDateString([], {weekday: "short", month: "short", day: "numeric", timeZone: tz}) : "—";
    const daylight = sun.sunrise && sun.sunset ? Math.round((sun.sunset - sun.sunrise) / 6e4) : null;
    box.hidden = false;
    box.innerHTML = `<h2>Sun &amp; moon</h2>
      <div class="sky"><div><span class="ic" aria-hidden="true">🌅</span><span class="dim">Sunrise</span><b>${t(sun.sunrise)}</b><span class="dim small">first light ${t(sun.dawn)}</span></div>
        <div><span class="ic" aria-hidden="true">🌇</span><span class="dim">Sunset</span><b>${t(sun.sunset)}</b><span class="dim small">last light ${t(sun.dusk)}</span></div>
        <div><span class="ic" aria-hidden="true">${ph.icon}</span><span class="dim">${esc(ph.name)}</span><b>${Math.round(ill.fraction * 100)}% lit</b>
          <span class="dim small">full ${dateOf(full)}</span></div>
        <div><span class="ic" aria-hidden="true">🌙</span><span class="dim">Moonrise</span><b>${moon.alwaysUp ? "up all day" : moon.alwaysDown ? "doesn't rise" : t(moon.rise)}</b>
          <span class="dim small">moonset ${moon.set ? t(moon.set) : "—"}</span></div></div>
      <p class="dim small">${daylight ? `${Math.floor(daylight / 60)} h ${daylight % 60} min of daylight. ` : ""}New moon ${dateOf(nw)}. Times for the middle of the ranch${tz ? ", ranch time" : ""}.</p>`;
  }

  // ---------------------------------------------------------------- MAP (2D Leaflet / 3D three.js)
  function loadLeaflet() {
    if (window.L) return Promise.resolve();
    return new Promise((ok, fail) => {
      const css = document.createElement("link"); css.rel = "stylesheet"; css.href = "vendor/leaflet/leaflet.css"; document.head.appendChild(css);
      const s = document.createElement("script"); s.src = "vendor/leaflet/leaflet.js"; s.onload = ok; s.onerror = fail; document.head.appendChild(s);
    });
  }
  function prow(p) {
    const s = STATUS[p.status] || STATUS.unknown;
    return `<li><button type="button" class="prow ${esc(p.status)}" data-pasture="${esc(p.id)}">
      <span class="badge" aria-hidden="true">${s.icon}</span><b>${esc(p.name)} <span class="chip ${esc(p.status)}">${s.word}</span></b>
      <span class="go" aria-hidden="true">›</span><span class="why">${esc(p.headline)}</span></button></li>`;
  }
  function setPressed(sel, attr, val) { document.querySelectorAll(sel).forEach(b => b.setAttribute("aria-pressed", String(b.dataset[attr] === String(val)))); }
  async function renderMap() {
    setPressed("[data-mapmode]", "mapmode", mapMode); setPressed("[data-look]", "look", look);
    $("lookSeg").hidden = $("exagRow").hidden = mapMode !== "3d";
    $("map").hidden = mapMode !== "2d"; $("map3d").hidden = mapMode !== "3d";
    $("m-list").innerHTML = snap ? snap.pastures.map(prow).join("") : "";
    renderLayerCard();
    if (!snap) { $("map-src").textContent = "No ranch data yet."; return; }
    if (mapMode === "3d") return render3d();
    if (view3d) { view3d.dispose(); view3d = null; }
    $("map-src").textContent = "Imagery: USGS The National Map. Tap a pasture or a pin.";
    try { await loadLeaflet(); } catch (e) { $("map").innerHTML = "<p class='dim' style='padding:16px'>Map couldn't load. The list below still works.</p>"; return; }
    if (!map) {
      map = L.map("map", {zoomControl: true});
      L.tileLayer("https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}",
        {maxZoom: 19, maxNativeZoom: 16, attribution: "USGS The National Map"}).addTo(map);
      map.on("click", e => { if (mapPicker) { const cb = mapPicker; mapPicker = null; $("map").style.cursor = ""; cb(e.latlng.lat, e.latlng.lng); } });
    }
    const first = !mapLayers.length;
    mapLayers.forEach(l => l.remove()); mapLayers = [];
    const all = [];
    snap.pastures.forEach(p => {
      const ll = p.outline.map(([lon, lat]) => [lat, lon]); all.push(...ll);
      if (!layers.pastures) return;
      const poly = L.polygon(ll, {color: "#fff", weight: 2, fillColor: layers.colors ? (COLOR[p.status] || "#888") : "#ffffff",
        fillOpacity: layers.colors ? .4 : .12}).on("click", () => { if (!mapPicker) openPastureSheet(p.id); });
      poly.bindTooltip(esc(p.name), {permanent: snap.pastures.length <= 8, direction: "center", className: "maplabel"});
      poly.addTo(map); mapLayers.push(poly);
    });
    mapItems().forEach(p => {
      const icon = L.divIcon({className: "", iconSize: [34, 34], iconAnchor: [17, 17], html:
        `<div class="photo-pin${p.flagged ? " flag" : ""}${p.place ? " place" : p.usgs ? " usgs" : p.report || p.task ? " report" : ""}">${p.heading_deg != null ? `<i class="cone" style="transform:rotate(${p.heading_deg}deg)"></i>` : ""}${p.icon}${p.n > 1 ? `<span class="n">${p.n}</span>` : ""}</div>`});
      const m = L.marker([p.lat, p.lon], {icon, title: p.title + (p.taken_at ? ", " + when(p.taken_at) : "")}).on("click", () => openItem(p.client_id));
      m.addTo(map); mapLayers.push(m);
    });
    map.invalidateSize(); if (first) map.fitBounds(all, {padding: [20, 20]});
  }
  function src3d() {
    const meta = view3d && view3d.meta; if (!meta) return;
    const ground = meta.dem_source === "usgs_3dep" ? `USGS lidar (${meta.dem_resolution_m} m)` : "EXAMPLE terrain, not your land";
    const skin = look === "topo" ? "Topo: elevation colors, contour lines" + (view3d.contourFt ? ` every ${view3d.contourFt()} ft` : "") + "."
      : meta.texture_source === "naip" ? "Aerial photo: USDA NAIP." : "Aerial photo unavailable; showing relief.";
    $("map-src").textContent = `Ground: ${ground}. ${skin} ${layers.colors ? "Glowing walls are pasture lines, colored by status." : "Pasture lines without warning colors."} Drag to turn, pinch to zoom.`;
  }
  async function render3d() {
    const box = $("map3d");
    if (view3d) { view3d.setLook(look); view3d.setPhotos(mapItems()); view3d.setStatuses(statusMap()); view3d.setPasturesVisible(layers.pastures); src3d(); return; }
    box.innerHTML = "<div class='busy'><div class='spinner'></div>Loading the lidar terrain…</div>";
    try {
      const [meta, height, texture, mod] = await Promise.all([api("terrain/meta"), getBytes("terrain/height"), getBytes("terrain/texture"), import("./terrain3d.js")]);
      if ($("v-map").hidden || mapMode !== "3d") return;
      const namesById = {}, lonlatById = {};
      snap.pastures.forEach(p => { namesById[p.id] = p.name; lonlatById[p.id] = p.outline; });
      view3d = mod.mount(box, {meta, height: height.bytes, texture, statusById: statusMap(), namesById, lonlatById, look, exaggeration: exag,
        photos: mapItems(), onPhoto: id => { if (!picking()) openItem(id); }, onPasture: id => { if (!picking()) openPastureSheet(id); }});
      view3d.meta = meta; view3d.setPasturesVisible(layers.pastures); src3d();
    } catch (e) {
      if (e.signin) { show("login"); return; }
      // No 3D yet (or no WebGL / no signal): fall back to the flat map so the console still works.
      const why = e.message === "notready" ? "The 3D terrain isn't ready yet, so here's the flat map." :
        navigator.onLine ? "The 3D view couldn't load, so here's the flat map." : "The 3D view needs signal the first time, so here's the flat map.";
      mapMode = "2d"; await renderMap(); $("map-src").textContent = why;
    }
  }
  let mapPicker = null;
  const picking = () => !!mapPicker || (view3d && view3d._picking);
  function pickOnMap(cb) {                       // "tap the map where it is"
    show("map");
    const done = (lat, lon) => { if (view3d) view3d._picking = false; $("pickBar").hidden = true; cb(lat, lon); };
    $("pickBar").hidden = false;
    $("pickCancel").onclick = () => { mapPicker = null; if (view3d) { view3d.cancelPick(); view3d._picking = false; } $("pickBar").hidden = true; cb(null, null); };
    setTimeout(() => {
      if (mapMode === "3d" && view3d) { view3d._picking = true; view3d.pickOnce(done); }
      else { mapPicker = done; $("map").style.cursor = "crosshair"; }
    }, 300);
  }
  function renderLayerCard() {
    const all = (() => { const keep = layers; layers = Object.fromEntries(LAYERS.map(([k]) => [k, true])); const x = mapItems(); layers = keep; return x; })();
    const count = k => all.filter(x => x.layer === k).length;
    $("layerCard").innerHTML = `<h2>Show on the map</h2><div class="layers">${LAYERS.map(([k, label, ic]) => `<button type="button" class="layer" data-layer="${k}"
      aria-pressed="${!!layers[k]}"><span aria-hidden="true">${ic}</span>${esc(label)}${["pastures", "colors"].includes(k) ? "" : ` <span class="dim">${count(k)}</span>`}</button>`).join("")}</div>
      <label class="switchrow"><input type="checkbox" id="hideEverydayMap" ${store.get("hideEveryday", false) ? "checked" : ""}>
        <span>Ignore drought &amp; rain in pasture status <span class="dim small">(they're the same everywhere)</span></span></label>`;
    $("layerCard").querySelectorAll("[data-layer]").forEach(b => b.onclick = () => {
      layers[b.dataset.layer] = !layers[b.dataset.layer]; store.set("layers", layers); renderMap(); });
    $("hideEverydayMap").onchange = e => setHideEveryday(e.target.checked);
  }
  document.querySelectorAll("[data-mapmode]").forEach(b => b.onclick = () => { mapMode = b.dataset.mapmode; renderMap(); });
  document.querySelectorAll("[data-look]").forEach(b => b.onclick = () => { look = b.dataset.look; store.set("look", look); setPressed("[data-look]", "look", look); if (view3d) view3d.setLook(look); renderMap(); });
  document.querySelectorAll("[data-exag]").forEach(b => b.onclick = () => { exag = Number(b.dataset.exag); setPressed("[data-exag]", "exag", exag); if (view3d) view3d.setExaggeration(exag); });
  $("resetView").onclick = () => view3d && view3d.reset();
  $("layersBtn").onclick = () => { $("layerCard").hidden = !$("layerCard").hidden; $("layersBtn").setAttribute("aria-pressed", String(!$("layerCard").hidden)); };
  $("addPlaceBtn").onclick = () => addPlace();

  function openPastureSheet(id) {
    const p = snap && snap.pastures.find(x => x.id === id); if (!p) return;
    const s = STATUS[p.status] || STATUS.unknown;
    const n = allPhotos().filter(x => x.pasture_id === id).length;
    openSheet(p.name, `<p><span class="chip ${esc(p.status)}">${s.icon} ${s.word}</span> ${esc(p.headline.replace(/^(Act|Watch):\s*/, ""))}</p>
      <p class="dim">${p.acres != null ? p.acres + " acres · " : ""}${n} photo${n === 1 ? "" : "s"}</p>
      <div class="row"><button type="button" class="primary" data-pasture="${esc(id)}">Open pasture</button>
      <button type="button" class="secondary" data-act="photo" data-here="1">📷 Photo here</button></div>`);
    currentPasture = id;
  }

  // ---------------------------------------------------------------- PASTURE
  function renderPasture() {
    const p = snap && snap.pastures.find(x => x.id === currentPasture);
    if (!p) { show("map"); return; }
    closeSheet();
    const s = STATUS[p.status] || STATUS.unknown;
    $("d-h").textContent = p.name; $("d-acres").textContent = p.acres != null ? p.acres + " acres" : "";
    $("d-status").innerHTML = `<span class="chip ${esc(p.status)}">${s.icon} ${s.word}</span> <span class="dim">${esc(p.headline.replace(/^(Act|Watch):\s*/, ""))}</span>`;
    const ph = allPhotos().filter(x => x.pasture_id === p.id).slice(0, 9);
    $("d-photos").innerHTML = "<h2>Photos</h2>" + (ph.length ? `<div class="photogrid">${ph.map(x => `<button type="button" data-photo="${esc(x.client_id)}"
      aria-label="Photo ${esc(when(x.taken_at))}"><img src="${esc(thumbOf(x))}" alt="" loading="lazy"></button>`).join("")}</div>` : "<p class='dim'>No photos here yet.</p>");
    $("d-signals").innerHTML = "<h2>Why</h2>" + p.signals.map(g => `<div class="sig"><span class="lv ${esc(g.level)}" aria-label="${esc(g.level)}">${LEVEL[g.level] || "?"}</span>
      <b>${esc(g.label)}</b><span>${esc(g.text)}</span><span class="src">${g.source ? esc(g.source) : ""}${g.as_of ? " · " + esc(when(g.as_of, false)) : ""}</span></div>`).join("");
    const t = p.terrain;
    $("d-land").innerHTML = "<h2>Lay of the land</h2>" + (t ? `<div class="stat">
      <div><span class="dim">Elevation</span><b>${t.elev_min_ft}–${t.elev_max_ft} ft</b></div>
      <div><span class="dim">Average slope</span><b>${t.mean_slope_pct}%</b></div>
      <div><span class="dim">Faces</span><b>${esc(t.faces || "–")}</b></div></div>
      <button type="button" class="secondary" id="see3d">⛰ See it in 3D</button>` : "<p class='dim'>Terrain not available yet.</p>");
    if ($("see3d")) $("see3d").onclick = () => { mapMode = "3d"; show("map"); };
  }

  // ---------------------------------------------------------------- LOG
  function logItems() {
    const q = store.get("queue", []).map(l => ({...l, _pending: true}));
    const logs = [...q, ...serverLogs.filter(l => !q.some(x => x.client_id === l.client_id))].map(l => ({type: l.kind === "note" ? "problem" : l.kind, at: l.logged_at, l}));
    const ph = allPhotos().map(p => ({type: "photo", at: p.taken_at, p}));
    return [...logs, ...ph].sort((a, b) => String(b.at).localeCompare(String(a.at)));
  }
  function itemHtml(it) {
    const by = x => x.by ? " · " + esc(x.by) : "";
    if (it.type === "photo") {
      const p = it.p, a = p.analysis || {};
      const tags = (p.tags || []).map(tagSpan).join("");
      return `<li class="clickable" data-photo="${esc(p.client_id)}"><img src="${esc(thumbOf(p))}" alt="" loading="lazy">
        <b>Photo${p.pasture_id ? " · " + esc(pastureName(p.pasture_id)) : ""}${p.heading_deg != null ? " · facing " + compass(p.heading_deg) : ""}</b>
        <span>${tags}${a.green_pct != null ? ` <span class="dim">${a.green_pct}% green</span>` : ""}</span>
        <span class="meta">${esc(when(p.taken_at))}${by(p)}${p._pending ? ' · <span class="pending">waiting to send</span>' : ""}</span></li>`;
    }
    const l = it.l;
    const top = topTag(l.tags), ico = it.type === "problem" ? (top ? TAG[top].icon : "📝") : {move: "🐄", rain: "🌧"}[it.type] || "•";
    const what = it.type === "move" ? `Moved cattle${l.from_pasture_id ? " from " + esc(pastureName(l.from_pasture_id)) : ""} to <b>${esc(pastureName(l.pasture_id))}</b>${l.head ? " (" + esc(l.head) + " head)" : ""}`
      : it.type === "rain" ? `Rain gauge: <b>${Number(l.inches).toFixed(2)} in</b>${l.pasture_id ? " at " + esc(pastureName(l.pasture_id)) : ""}`
      : `${(l.tags || []).map(tagSpan).join("")} ${esc(l.text || "")}${l.pasture_id ? ` <span class="dim">(${esc(pastureName(l.pasture_id))})</span>` : ""}${l.lat != null ? " 📍" : ""}`;
    return `<li${it.type === "problem" ? ` class="clickable" data-photo="${esc(l.client_id)}"` : ""}><span class="ico" aria-hidden="true">${ico}</span><span>${what}</span><span></span>
      <span class="meta">${esc(when(l.logged_at))}${by(l)}${l._pending ? ' · <span class="pending">waiting to send</span>' : ""}</span></li>`;
  }
  function renderLog() {
    setPressed("[data-filter]", "filter", logFilter);
    const n = store.get("queue", []).length + pending.length;
    $("g-queue").hidden = !n;
    $("g-queue").innerHTML = `<p><b>${n} waiting to send.</b> Safe on this phone; they'll send by themselves when there's signal.</p>
      <button type="button" class="secondary" id="syncNow">Send now</button>`;
    if ($("syncNow")) $("syncNow").onclick = () => syncAll(true);
    const tagsOf = i => (i.p || i.l).tags || [];
    const items = logItems().filter(i => logFilter === "all" || i.type === logFilter
      || (logFilter === "problem" && (i.type === "photo" || i.type === "problem") && (tagsAt(tagsOf(i), HEADS_UP).length || (i.p && i.p.flagged)))
      || (logFilter === "wildlife" && tagsOf(i).some(t => TAG[t] && TAG[t].group === "Wildlife"))).slice(0, 80);
    $("g-list").innerHTML = items.length ? items.map(itemHtml).join("") : "<li class='dim'>Nothing yet. Use the buttons on Home.</li>";
  }
  document.querySelectorAll("[data-filter]").forEach(b => b.onclick = () => { logFilter = b.dataset.filter; renderLog(); });

  // ---------------------------------------------------------------- MORE (crew, settings)
  async function renderMore() {
    $("o-who").textContent = me ? `${me.name}${me.role === "crew" ? " · crew" : ""} · ${me.ranch}` : "";
    $("o-everyday").checked = store.get("hideEveryday", false);
    $("o-everyday").onchange = e => setHideEveryday(e.target.checked);
    const rs = (me && me.ranches) || [];
    $("o-ranch").hidden = rs.length < 2;
    $("o-ranch").innerHTML = `<h2>Your ranches</h2><div class="row">${rs.map(r => `<button type="button" class="${r.workspace_id === me.workspace_id ? "primary" : "secondary"}"
      data-ranch="${esc(r.workspace_id)}">${esc(r.name)}</button>`).join("")}</div><p class="dim small">You can also tap the ranch name at the top.</p>`;
    $("o-console").hidden = !isOwner();
    $("o-sources").innerHTML = ((snap && snap.sources) || []).map(s => `<li><span><b>${esc(s.name)}</b><br><span class="${s.live ? "ok-txt" : "no-txt"}">${s.live ? "Working" : s.demo ? "Demo values" : "Not available"}</span></span>
      <span class="when">${s.as_of ? esc(when(s.as_of, false)) : ""}</span></li>`).join("") || "<li class='dim'>No data yet.</li>";
    const crew = $("o-crew");
    crew.hidden = !(me && me.role === "owner");
    if (crew.hidden) return;
    crew.innerHTML = "<h2>Your crew</h2><p class='dim'>Loading…</p>";
    try {
      const c = await api("crew");
      crew.innerHTML = `<h2>Your crew</h2>
        <p class="dim">Give a ranch hand a <b>crew code</b>. They tap <b>Join a ranch crew</b> when they open RangeIQ. Hands can see the ranch, take photos, log work and check off jobs, but can't change settings.</p>
        <p class="dim">A <b>partner code</b> is for a co-owner or manager: same rights as you, including the crew. It works once and lasts 2 days. Someone who already has a RangeIQ login uses it with their own email and password, and gets both ranches in one app.</p>
        ${c.invites.map(i => `<div class="row" style="align-items:center"><b style="font-size:1.5rem;letter-spacing:.08em">${esc(i.code)}</b>
          <span class="dim small">${i.role === "owner" ? "<b>partner</b> · " : "crew · "}until ${esc(when(i.expires_at, false))} · used ${i.uses}/${i.max_uses}</span>
          <button type="button" class="pill" data-revoke="${esc(i.code)}">Stop code</button></div>`).join("")}
        <div class="row"><button type="button" class="primary" id="newCode">Make a crew code</button>
          <button type="button" class="secondary" id="newPartner">Make a partner code</button></div>
        ${c.members.length ? `<h3>People on this ranch</h3><ul class="srclist">${c.members.map(m => `<li><span><b>${esc(m.name)}</b><br><span class="dim small">${m.role === "owner" ? "partner" : "crew"} · joined ${esc(when(m.joined_at, false))}</span></span>
          <button type="button" class="pill" data-remove="${esc(m.user_id)}">Remove</button></li>`).join("")}</ul>` : ""}`;
      $("newCode").onclick = async () => { try { await api("crew/invites", {method: "POST", body: "{}"}); renderMore(); } catch (e) { toast(e.message); } };
      $("newPartner").onclick = async () => { try { await api("crew/invites", {method: "POST", body: JSON.stringify({role: "partner"})}); renderMore(); } catch (e) { toast(e.message); } };
      crew.querySelectorAll("[data-revoke]").forEach(b => b.onclick = async () => { await api("crew/invites/" + encodeURIComponent(b.dataset.revoke), {method: "DELETE"}); renderMore(); });
      crew.querySelectorAll("[data-remove]").forEach(b => b.onclick = async () => {
        if (!confirm("Remove this person from your crew? They'll be signed out.")) return;
        await api("crew/members/" + encodeURIComponent(b.dataset.remove), {method: "DELETE"}); renderMore(); });
    } catch (e) { crew.innerHTML = "<h2>Your crew</h2><p class='dim'>Crew settings need signal.</p>"; }
  }
  function setSize(v) { document.documentElement.style.setProperty("--scale", v); store.set("scale", v); setPressed("[data-size]", "size", v); }
  document.querySelectorAll("[data-size]").forEach(b => b.onclick = () => setSize(b.dataset.size));
  setSize(store.get("scale", "1"));
  $("logoutBtn").onclick = async () => {
    if ((store.get("queue", []).length || pending.length) && !confirm("Some photos or entries haven't been sent yet. Sign out anyway? They stay on this phone.")) return;
    try { await api("logout", {method: "POST"}); } catch (e) {}
    ["token", "snapshot", "snapshotAt", "serverLogs", "photos", "me", "tasks", "people", "places"].forEach(k => store.del(k)); rawSnap = snap = null; me = null; photos = []; show("login");
  };

  // ---------------------------------------------------------------- sheets
  function openSheet(title, html) { $("sheetTitle").textContent = title; $("sheetBody").innerHTML = html; $("sheet").hidden = false; $("sheetBack").hidden = false; }
  function closeSheet() { $("sheet").hidden = true; $("sheetBack").hidden = true; $("sheetBody").innerHTML = ""; }
  $("sheetBack").onclick = closeSheet;
  function pastureOptions(selected, blank) {
    return (blank ? `<option value="">${esc(blank)}</option>` : "") + ((snap && snap.pastures) || [])
      .map(p => `<option value="${esc(p.id)}" ${p.id === selected ? "selected" : ""}>${esc(p.name)}</option>`).join("");
  }
  function tagChips(selected = []) {
    return `<div class="tagpick" role="group" aria-label="What did you see?">${TAG_GROUPS.map(g => `<details class="tgroup" name="tg">
      <summary><span aria-hidden="true">${g.icon}</span> ${esc(g.group)} <span class="n"></span></summary>
      <div class="tagchips">${g.tags.map(([t, level]) => `<button type="button" class="${level === "good" ? "goodtag" : level === "info" || level === "alert" ? "infotag" : ""}"
        data-tag="${esc(t)}" aria-pressed="${selected.includes(t)}">${esc(t)}</button>`).join("")}</div></details>`).join("")}
      <p class="picked dim" aria-live="polite"></p></div>`;
  }
  function wireChips(root) {
    const update = () => {
      root.querySelectorAll(".tgroup").forEach(d => { const n = d.querySelectorAll("[aria-pressed='true']").length; d.querySelector(".n").textContent = n ? `(${n})` : ""; });
      const picked = chosenTags(root), out = root.querySelector(".picked");
      if (out) out.innerHTML = picked.length ? "Picked: " + picked.map(tagSpan).join(" ") : "";
    };
    root.querySelectorAll("[data-tag]").forEach(b => b.onclick = () => { b.setAttribute("aria-pressed", String(b.getAttribute("aria-pressed") !== "true")); update(); });
    update();
  }
  const chosenTags = root => [...root.querySelectorAll("[data-tag][aria-pressed='true']")].map(b => b.dataset.tag);

  // ---------------------------------------------------------------- quick logs (rain, move, report)
  function act(kind, here) {
    if (kind === "photo") return takePhoto(here);
    const now = new Date(), local = new Date(now - now.getTimezoneOffset() * 6e4).toISOString().slice(0, 16);
    let html, title;
    if (kind === "rain") {
      title = "Rain gauge";
      html = `<label>Inches<input type="number" name="inches" inputmode="decimal" min="0" max="20" step="0.01" required></label>
        <div class="quick">${[0.1, 0.25, 0.5, 1].map(v => `<button type="button" data-in="${v}">${v.toFixed(2)}</button>`).join("")}</div>
        <label>Which gauge? (optional)<select name="pasture_id">${pastureOptions(here, "Ranch gauge")}</select></label>`;
    } else if (kind === "move") {
      title = "Moved cattle";
      html = `<label>Into<select name="pasture_id" required>${pastureOptions(here, "Choose pasture")}</select></label>
        <label>Out of (optional)<select name="from_pasture_id">${pastureOptions(null, "—")}</select></label>
        <label>Head (optional)<input type="number" name="head" inputmode="numeric" min="0" step="1"></label>`;
    } else {
      kind = "report"; title = "Report what you saw";
      startSensors();                         // inside the tap, so the phone allows GPS
      html = `<p class="dim">Problems and sightings: a broken fence, a washed-out road, hogs, a snake, deer. Open a group and tap what you saw.</p>${tagChips()}
        <p class="dim" id="repWhere">📍 Getting your location…</p>
        <label>Where?<select name="pasture_id">${pastureOptions(here, "Whole ranch / not sure")}</select></label>
        <label>Anything else? (optional)<textarea name="text" maxlength="2000" placeholder="Which trough, how many head, which gate…"></textarea></label>`;
    }
    openSheet(title, `<form class="form" id="actForm">${html}<label>When<input type="datetime-local" name="logged_at" value="${local}"></label>
      <div class="row"><button type="submit" class="primary">Save</button><button type="button" class="secondary" id="actCancel">Cancel</button></div></form>`);
    const f = $("actForm"); wireChips(f);
    f.querySelectorAll("[data-in]").forEach(b => b.onclick = () => { f.inches.value = b.dataset.in; });
    let whereTimer = null;
    if (kind === "report") whereTimer = setInterval(() => {
      const w = $("repWhere"); if (!w) { clearInterval(whereTimer); return; }
      const fx = cam.fix && Date.now() - cam.fix.at < 120000 ? cam.fix : null;
      w.textContent = fx ? `📍 Your location will be saved with this report (±${fx.acc} m), so it shows on the map.` : "📍 Getting your location… (the report saves without it if there's no GPS)";
      if (fx && !here && f.pasture_id && !f.pasture_id.dataset.touched) { const pid = pastureAt(fx.lon, fx.lat); if (pid) f.pasture_id.value = pid; }
    }, 1000);
    if (f.pasture_id) f.pasture_id.addEventListener("change", () => { f.pasture_id.dataset.touched = "1"; });
    const done = () => { clearInterval(whereTimer); if (kind === "report") stopSensors(); };
    $("actCancel").onclick = () => { done(); closeSheet(); };
    f.onsubmit = e => {
      e.preventDefault();
      const d = Object.fromEntries(new FormData(f).entries());
      const entry = {client_id: uid(), kind: kind === "report" ? "note" : kind, logged_at: new Date(d.logged_at || Date.now()).toISOString(), by: me && me.name};
      if (d.pasture_id) entry.pasture_id = d.pasture_id;
      if (kind === "move") { if (d.from_pasture_id && d.from_pasture_id !== d.pasture_id) entry.from_pasture_id = d.from_pasture_id; if (d.head) entry.head = Number(d.head); }
      if (kind === "rain") entry.inches = Number(d.inches);
      if (kind === "report") {
        entry.tags = chosenTags(f); entry.text = (d.text || "").trim();
        if (!entry.tags.length && !entry.text) { toast("Tap what you saw, or write a note."); return; }
        const fx = cam.fix && Date.now() - cam.fix.at < 120000 ? cam.fix : null;
        if (fx) { entry.lat = fx.lat; entry.lon = fx.lon; entry.accuracy_m = fx.acc; }
      }
      done();
      const q = store.get("queue", []); q.push(entry); store.set("queue", q);
      closeSheet(); toast(navigator.onLine ? "Saved." : "Saved on this phone. It'll send when there's signal.");
      rerender(); syncAll();
    };
  }

  // ---------------------------------------------------------------- CAMERA: photo + GPS + direction + on-phone analysis
  const cam = {heading: null, headingAt: 0, fix: null, watchId: null, listening: false};
  function onOrient(e) {
    let h = null;
    if (typeof e.webkitCompassHeading === "number") h = e.webkitCompassHeading;                // iPhone
    else if ((e.absolute || e.type === "deviceorientationabsolute") && e.alpha != null) h = (360 - e.alpha) % 360;  // Android
    if (h != null) { cam.heading = h; cam.headingAt = Date.now(); }
  }
  function startSensors() {
    if (!cam.listening) {
      const add = () => { addEventListener("deviceorientationabsolute", onOrient, true); addEventListener("deviceorientation", onOrient, true); cam.listening = true; };
      if (typeof DeviceOrientationEvent !== "undefined" && typeof DeviceOrientationEvent.requestPermission === "function")
        DeviceOrientationEvent.requestPermission().then(r => { if (r === "granted") add(); }).catch(() => {});   // iPhone asks once
      else add();
    }
    if (navigator.geolocation && cam.watchId == null) cam.watchId = navigator.geolocation.watchPosition(p => {
      const f = {lat: p.coords.latitude, lon: p.coords.longitude, acc: Math.round(p.coords.accuracy), at: Date.now()};
      if (!cam.fix || f.acc <= cam.fix.acc || Date.now() - cam.fix.at > 30000) cam.fix = f;
    }, () => {}, {enableHighAccuracy: true, maximumAge: 15000, timeout: 30000});
  }
  function stopSensors() { if (cam.watchId != null) { navigator.geolocation.clearWatch(cam.watchId); cam.watchId = null; } }
  function waitForFix(ms) {
    return new Promise(ok => { const t0 = Date.now(); (function poll() {
      if ((cam.fix && cam.fix.acc <= 30 && Date.now() - cam.fix.at < 60000) || Date.now() - t0 > ms) return ok(cam.fix && Date.now() - cam.fix.at < 120000 ? cam.fix : null);
      setTimeout(poll, 250); })(); });
  }
  function takePhoto(here) {
    photoHere = here || null;
    startSensors();                       // must start inside the tap so the phone allows GPS/compass
    cam.fix = cam.fix && Date.now() - cam.fix.at < 60000 ? cam.fix : null;
    const input = $("camInput"); input.value = ""; input.onchange = onCam; input.click();
  }
  const onCam = e => { const file = e.target.files && e.target.files[0]; if (file) processPhoto(file); };
  $("camInput").onchange = onCam;

  function loadImage(file) {
    return new Promise((ok, fail) => { const url = URL.createObjectURL(file), img = new Image();
      img.onload = () => ok(img); img.onerror = () => { URL.revokeObjectURL(url); fail(new Error("That file isn't a photo the phone can read.")); }; img.src = url; });
  }
  function toJpeg(img, maxSide, quality) {
    const s = Math.min(1, maxSide / Math.max(img.naturalWidth, img.naturalHeight));
    const c = document.createElement("canvas"); c.width = Math.round(img.naturalWidth * s); c.height = Math.round(img.naturalHeight * s);
    c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
    return new Promise(ok => c.toBlob(b => ok(b), "image/jpeg", quality));
  }
  // Green cover with the Canopeo rule (Patrignani & Ochsner 2015): R/G < 0.95, B/G < 0.95, 2G-R-B > 20.
  // Sky is left out; tan/brown pixels are "brown or bare" (dry grass and bare soil look alike in a photo).
  function analyze(img) {
    const W = 200, H = Math.max(1, Math.round(img.naturalHeight / img.naturalWidth * W));
    const c = document.createElement("canvas"); c.width = W; c.height = H;
    const g = c.getContext("2d", {willReadFrequently: true}); g.drawImage(img, 0, 0, W, H);
    const d = g.getImageData(0, 0, W, H).data;
    let ground = 0, green = 0, brown = 0, sky = 0;
    for (let i = 0, px = 0; i < d.length; i += 4, px++) {
      const r = d[i], gg = d[i + 1], b = d[i + 2], y = Math.floor(px / W), bright = (r + gg + b) / 3;
      if ((b > r + 12 && b >= gg && bright > 100) || (bright > 220 && y < H * 0.55)) { sky++; continue; }
      ground++;
      if (gg > 0 && r / gg < 0.95 && b / gg < 0.95 && 2 * gg - r - b > 20) green++;
      else if (r > b + 15 && r >= gg - 8 && bright > 60) brown++;
    }
    const pct = n => ground ? Math.round(100 * n / ground) : null;
    return {green_pct: pct(green), brown_bare_pct: pct(brown), sky_pct: Math.round(100 * sky / (W * H)), method: "canopeo-rgb"};
  }
  function previousAtSpot(fix, heading) {
    return allPhotos().filter(p => p.lat != null && p.analysis && p.analysis.green_pct != null && metres(fix, p) <= 35 &&
      (heading == null || p.heading_deg == null || Math.abs(((heading - p.heading_deg + 540) % 360) - 180) <= 45))[0] || null;
  }
  async function processPhoto(file) {
    openSheet("New photo", "<div class='busy'><div class='spinner'></div>Getting the photo, location and direction…</div>");
    let img;
    try { img = await loadImage(file); } catch (e) { closeSheet(); toast(e.message); return; }
    const [photo, thumb] = await Promise.all([toJpeg(img, 1600, 0.82), toJpeg(img, 360, 0.7)]);
    const analysis = analyze(img); URL.revokeObjectURL(img.src);
    const fix = await waitForFix(6000);
    const heading = cam.heading != null && Date.now() - cam.headingAt < 90000 ? Math.round(cam.heading) : null;
    stopSensors();
    const guess = photoHere || (fix ? pastureAt(fix.lon, fix.lat) : null);
    const prev = fix ? previousAtSpot(fix, heading) : null;
    const delta = prev ? analysis.green_pct - prev.analysis.green_pct : null;
    const previewUrl = URL.createObjectURL(photo);
    const where = fix ? `${guess ? "📍 " + esc(pastureName(guess)) : "📍 Outside your pastures"} · ±${fix.acc} m` : "📍 No GPS fix. Pick the pasture below.";
    openSheet("New photo", `<img class="photoimg" src="${previewUrl}" alt="The photo you just took">
      <p>${where}${heading != null ? ` · 🧭 facing <b>${compass(heading)}</b>` : ""}</p>
      <div class="stat"><div><span class="dim">Green</span><b>${analysis.green_pct ?? "–"}%</b></div>
        <div><span class="dim">Brown or bare</span><b>${analysis.brown_bare_pct ?? "–"}%</b></div>
        ${prev ? `<div><span class="dim">Same spot, ${esc(when(prev.taken_at, false))}</span><b>${delta > 0 ? "+" : ""}${delta} pts</b></div>` : ""}</div>
      ${prev && delta <= -15 ? `<p class="error">Much less green than the last photo from this spot.</p>` : ""}
      <form class="form" id="photoForm"><p><b>What does it show?</b> (optional)</p>${tagChips()}
        <label>Pasture<select name="pasture_id">${pastureOptions(guess, "Not in a pasture")}</select></label>
        <label>Note (optional)<textarea name="note" maxlength="2000" placeholder="Tank about a quarter full, fence down by the north gate…"></textarea></label>
        <div class="row"><button type="submit" class="primary">Save photo</button><button type="button" class="secondary" id="photoCancel">Discard</button></div></form>
      <p class="src">Green is measured from the colors in the photo (Canopeo method). It's most useful comparing photos from the same spot over time.</p>`);
    const f = $("photoForm"); wireChips(f);
    $("photoCancel").onclick = () => { URL.revokeObjectURL(previewUrl); closeSheet(); };
    f.onsubmit = async e => {
      e.preventDefault();
      const tags = chosenTags(f), d = Object.fromEntries(new FormData(f).entries());
      const client_id = uid();
      const meta = {client_id, taken_at: new Date().toISOString(), lat: fix ? fix.lat : null, lon: fix ? fix.lon : null, accuracy_m: fix ? fix.acc : null,
        heading_deg: heading, pasture_id: d.pasture_id || null, tags, note: (d.note || "").trim() || null, by: me && me.name,
        analysis: {...analysis, compared_to: prev ? prev.client_id : null, green_change_pts: delta},
        flagged: tagsAt(tags, HEADS_UP).length > 0 || (delta != null && delta <= -15)};
      try { await idb.put({client_id, meta, photo, thumb}); }
      catch (err) { toast("Couldn't save the photo on this phone: " + err.message); return; }
      URL.revokeObjectURL(previewUrl); closeSheet();
      toast(navigator.onLine ? "Photo saved. Sending…" : "Photo saved on this phone. It'll send when there's signal.");
      await loadPending(); rerender(); syncAll();
    };
  }

  function openReport(id) {
    const it = logItems().find(i => i.type === "problem" && i.l.client_id === id); if (!it) return;
    const l = it.l, mine = me && me.user_id && l.user_id === me.user_id;
    openSheet(l.pasture_id ? pastureName(l.pasture_id) : "Report", `<p>${(l.tags || []).map(tagSpan).join(" ")}</p>
      ${l.text ? `<p>${esc(l.text)}</p>` : ""}
      <p class="dim">${esc(when(l.logged_at))}${l.by ? " · " + esc(l.by) : ""}${l.accuracy_m ? " · 📍 ±" + l.accuracy_m + " m" : l.lat == null ? " · no location" : ""}</p>
      ${l._pending ? "<p class='pending'>Waiting to send.</p>" : ""}
      <div class="row"><button type="button" class="primary" id="rpJob">＋ Make it a job</button>${l.lat != null ? `<button type="button" class="secondary" id="rpMap">Show on map</button>` : ""}
      ${l._pending || isOwner() || mine ? `<button type="button" class="secondary" id="rpDel">Delete</button>` : ""}</div>`);
    $("rpJob").onclick = () => window.__rangeiqMakeJob(l, false);
    if ($("rpMap")) $("rpMap").onclick = () => showOnMap(l.lat, l.lon);
    if ($("rpDel")) $("rpDel").onclick = async () => {
      if (!confirm("Delete this report?")) return;
      try {
        if (l._pending) store.set("queue", store.get("queue", []).filter(x => x.client_id !== id));
        else await api("logs/" + encodeURIComponent(id), {method: "DELETE"});
        serverLogs = serverLogs.filter(x => x.client_id !== id); store.set("serverLogs", serverLogs); closeSheet(); rerender();
      } catch (e) { toast(e.message); }
    };
  }
  function openPhoto(id) {
    const p = allPhotos().find(x => x.client_id === id); if (!p) return openReport(id);
    const a = p.analysis || {}, spot = sameSpot(p);
    const canDelete = p._pending || isOwner() || (me && me.user_id && p.user_id === me.user_id);
    openSheet(p.pasture_id ? pastureName(p.pasture_id) : "Photo", `<img class="photoimg" src="${esc(imageOf(p))}" alt="Photo taken ${esc(when(p.taken_at))}">
      <p>${esc(when(p.taken_at))}${p.by ? " · " + esc(p.by) : ""}${p.heading_deg != null ? " · facing " + compass(p.heading_deg) : ""}${p.accuracy_m ? " · ±" + p.accuracy_m + " m" : ""}</p>
      <p>${(p.tags || []).map(tagSpan).join(" ")}</p>
      ${p.note ? `<p>${esc(p.note)}</p>` : ""}
      <div class="stat"><div><span class="dim">Green</span><b>${a.green_pct ?? "–"}%</b></div><div><span class="dim">Brown or bare</span><b>${a.brown_bare_pct ?? "–"}%</b></div>
      ${a.green_change_pts != null ? `<div><span class="dim">vs. last photo here</span><b>${a.green_change_pts > 0 ? "+" : ""}${a.green_change_pts} pts</b></div>` : ""}</div>
      ${p._pending ? "<p class='pending'>Waiting to send.</p>" : ""}
      ${spot.length > 1 ? `<h3>This spot over time</h3><div class="spotrow">${spot.map(x => `<button type="button" data-photo="${esc(x.client_id)}"
        ${x.client_id === p.client_id ? 'aria-current="true"' : ""}><img src="${esc(thumbOf(x))}" alt="" loading="lazy"><span>${esc(when(x.taken_at, false))}<br>
        <b>${(x.analysis || {}).green_pct ?? "–"}% green</b></span></button>`).join("")}</div>` : ""}
      <div class="row"><button type="button" class="primary" id="phJob">＋ Make it a job</button>${p.lat != null ? `<button type="button" class="secondary" id="phMap">Show on map</button>` : ""}
      ${canDelete ? `<button type="button" class="secondary" id="phDel">Delete</button>` : ""}</div>`);
    $("phJob").onclick = () => window.__rangeiqMakeJob(p, true);
    if ($("phMap")) $("phMap").onclick = () => showOnMap(p.lat, p.lon);
    if ($("phDel")) $("phDel").onclick = async () => {
      if (!confirm("Delete this photo?")) return;
      try {
        if (p._pending) await idb.del(p.client_id); else await api("photos/" + encodeURIComponent(p.client_id), {method: "DELETE"});
        photos = photos.filter(x => x.client_id !== p.client_id); store.set("photos", photos); await loadPending(); closeSheet(); rerender();
      } catch (e) { toast(e.message); }
    };
  }


  // ---------------------------------------------------------------- TO DO: jobs around the ranch
  // Anyone on the ranch can add a job; anyone can check it off. Changes are saved on the phone and sent when there's signal.
  let tasks = store.get("tasks", []), people = store.get("people", []);
  const REPEATS = [[0, "Just once"], [1, "Every day"], [2, "Every 2 days"], [3, "Every 3 days"], [7, "Every week"], [14, "Every 2 weeks"], [30, "Every month"]];
  const JOB_IDEAS = ["Check waters", "Fix fence", "Check cattle", "Put out mineral / salt", "Check windmill", "Grade road", "Spray weeds"];
  const localDay = (d = new Date()) => new Date(d - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 10);
  const addDays = (iso, n) => localDay(new Date(new Date(iso + "T12:00:00").getTime() + n * 864e5));
  const personName = id => (people.find(p => p.user_id === id) || {}).name || "";
  function applyTaskOp(op) {
    const i = tasks.findIndex(t => t.task_id === op.task_id), t = tasks[i];
    if (op.op === "add" && !t) tasks.push({task_id: op.task_id, title: op.title, note: op.note || null, pasture_id: op.pasture_id || null,
      due_date: op.due_date || null, repeat_days: op.repeat_days || 0, assignee_id: op.assignee_id || null, lat: op.lat ?? null, lon: op.lon ?? null,
      source_id: op.source_id || null, created_by: me && me.user_id, created_by_name: me && me.name, created_at: op.at, done_at: null, history: []});
    if (!t) return;
    if (op.op === "done") {
      t.history = [{op: "done", by: me && me.name, at: op.at}, ...(t.history || [])];
      if (t.repeat_days) { t._prevDue = t.due_date; t.due_date = addDays(localDay(new Date(op.at)), t.repeat_days); }
      else { t.done_at = op.at; t.done_by = me && me.user_id; t.done_by_name = me && me.name; }
    }
    if (op.op === "undo") {
      if (t.repeat_days) { if (t._prevDue !== undefined) t.due_date = t._prevDue; }
      else { t.done_at = null; t.done_by = null; t.done_by_name = null; }
      t.history = (t.history || []).slice(1);
    }
    if (op.op === "delete") tasks.splice(i, 1);
  }
  function taskOp(op) {
    op = {op_id: uid(), at: new Date().toISOString(), ...op};
    applyTaskOp(op); store.set("tasks", tasks);
    const q = store.get("taskq", []); q.push(op); store.set("taskq", q);
    rerender(); syncAll();
  }
  async function loadTasks() {
    try { const d = await api("tasks"); people = d.people || []; store.set("people", people); setTasksFromServer(d.tasks); } catch (e) { if (e.signin) throw e; }
  }
  function setTasksFromServer(list) {
    tasks = list || []; store.get("taskq", []).forEach(applyTaskOp); store.set("tasks", tasks);   // keep unsent changes on top
  }
  function taskBucket(t) {
    if (t.done_at) return "done";
    if (!t.due_date) return "any";
    const today = localDay();
    return t.due_date < today ? "late" : t.due_date === today ? "today" : "soon";
  }
  function dueText(t) {
    if (t.done_at) return `Done ${when(t.done_at)}${t.done_by_name ? " by " + t.done_by_name : ""}`;
    if (!t.due_date) return "Any time";
    const today = localDay(), d = t.due_date;
    if (d < today) { const n = Math.round((new Date(today) - new Date(d)) / 864e5); return n === 1 ? "Was due yesterday" : `Was due ${n} days ago`; }
    if (d === today) return "Due today";
    if (d === addDays(today, 1)) return "Due tomorrow";
    return "Due " + new Date(d + "T12:00:00").toLocaleDateString([], {weekday: "short", month: "short", day: "numeric"});
  }
  function taskRow(t) {
    const done = !!t.done_at, last = (t.history || [])[0];
    const bits = [dueText(t), t.repeat_days ? "🔁 " + REPEATS.find(r => r[0] === t.repeat_days)[1].toLowerCase() : "",
      t.pasture_id ? pastureName(t.pasture_id) : "", t.assignee_id ? "for " + personName(t.assignee_id) : "",
      t.repeat_days && last && last.op === "done" ? `last done ${when(last.at)} by ${last.by}` : ""].filter(Boolean);
    return `<li class="task ${taskBucket(t)}"><button type="button" class="check" data-check="${esc(t.task_id)}" aria-pressed="${done}"
        aria-label="${done ? "Mark not done" : "Check off"}: ${esc(t.title)}">${done ? "✓" : ""}</button>
      <button type="button" class="tbody" data-task="${esc(t.task_id)}"><b>${esc(t.title)}</b><span class="meta">${esc(bits.join(" · "))}</span></button></li>`;
  }
  function sortedOpen() {
    const order = {late: 0, today: 1, soon: 2, any: 3};
    return tasks.filter(t => !t.done_at).sort((a, b) => order[taskBucket(a)] - order[taskBucket(b)] || String(a.due_date || "9").localeCompare(String(b.due_date || "9"))
      || String(a.created_at).localeCompare(String(b.created_at)));
  }
  function renderTodo() {
    const open = sortedOpen(), done = tasks.filter(t => t.done_at).sort((a, b) => String(b.done_at).localeCompare(String(a.done_at)));
    const mine = me && me.user_id, groups = [["late", "Overdue"], ["today", "Today"], ["soon", "Coming up"], ["any", "Any time"]];
    const filt = store.get("todoMine", false) ? (t => !t.assignee_id || t.assignee_id === mine) : (() => true);
    $("t-mine").setAttribute("aria-pressed", String(store.get("todoMine", false)));
    $("t-list").innerHTML = groups.map(([k, label]) => { const list = open.filter(t => taskBucket(t) === k && filt(t));
        return list.length ? `<h2>${label}</h2><ul class="tasks">${list.map(taskRow).join("")}</ul>` : ""; }).join("")
      || `<div class="allclear"><span class="big-ok" aria-hidden="true">✓</span><span>Nothing to do. Add a job with the button above.</span></div>`;
    $("t-done").innerHTML = done.length ? `<details class="card"><summary><h2>Done in the last 2 weeks (${done.length})</h2></summary>
      <ul class="tasks">${done.map(taskRow).join("")}</ul></details>` : "";
  }
  function homeTodo() {
    const open = sortedOpen().filter(t => ["late", "today"].includes(taskBucket(t)));
    const box = $("h-todo");
    box.hidden = !open.length;
    if (open.length) box.innerHTML = `<h2>To do today <span class="dim">(${open.length})</span></h2><ul class="tasks">${open.slice(0, 4).map(taskRow).join("")}</ul>
      <button type="button" class="linkbtn" data-go="todo">All jobs ›</button>`;
  }
  $("t-mine").onclick = () => { store.set("todoMine", !store.get("todoMine", false)); renderTodo(); };
  $("t-add").onclick = () => addTask();
  document.addEventListener("click", e => {
    const c = e.target.closest("[data-check]");
    if (c) { const t = tasks.find(x => x.task_id === c.dataset.check); if (!t) return;
      if (t.done_at) taskOp({op: "undo", task_id: t.task_id});
      else { taskOp({op: "done", task_id: t.task_id}); toast(t.repeat_days ? `Done. Next: ${dueText(tasks.find(x => x.task_id === t.task_id))}.` : "Done. Nice work."); }
      return; }
    const b = e.target.closest("[data-task]"); if (b) openTask(b.dataset.task);
  });
  function openTask(id) {
    const t = tasks.find(x => x.task_id === id); if (!t) return;
    const canDelete = isOwner() || (me && t.created_by === me.user_id);
    openSheet(t.title, `${t.note ? `<p>${esc(t.note)}</p>` : ""}
      <p class="dim">${esc(dueText(t))}${t.repeat_days ? " · 🔁 " + esc(REPEATS.find(r => r[0] === t.repeat_days)[1].toLowerCase()) : ""}
        ${t.pasture_id ? " · " + esc(pastureName(t.pasture_id)) : ""}${t.assignee_id ? " · for " + esc(personName(t.assignee_id)) : ""}</p>
      <p class="dim small">Added by ${esc(t.created_by_name || "?")} ${esc(when(t.created_at))}</p>
      ${(t.history || []).length ? `<h3>History</h3><ul class="srclist">${t.history.map(h => `<li><span>${h.op === "done" ? "✓ Checked off" : "↩ Undone"} by ${esc(h.by || "?")}</span>
        <span class="when">${esc(when(h.at))}</span></li>`).join("")}</ul>` : ""}
      <div class="row"><button type="button" class="primary" data-check="${esc(t.task_id)}">${t.done_at ? "Mark not done" : "✓ Check off"}</button>
      ${t.lat != null ? `<button type="button" class="secondary" id="tkMap">Show on map</button>` : ""}
      ${t.source_id ? `<button type="button" class="secondary" data-photo="${esc(t.source_id)}">See the report</button>` : ""}
      ${canDelete ? `<button type="button" class="secondary" id="tkDel">Delete</button>` : ""}</div>`);
    $("sheetBody").querySelector("[data-check]").addEventListener("click", () => setTimeout(closeSheet, 50));
    if ($("tkMap")) $("tkMap").onclick = () => showOnMap(t.lat, t.lon);
    if ($("tkDel")) $("tkDel").onclick = () => { if (confirm("Delete this job?")) { taskOp({op: "delete", task_id: t.task_id}); closeSheet(); } };
  }
  function addTask(pre = {}) {
    const today = localDay();
    openSheet("Add a job", `<form class="form" id="taskForm">
      <label>What needs doing?<input name="title" maxlength="120" required value="${esc(pre.title || "")}" placeholder="Fix the fence by the north gate"></label>
      <div class="quick">${JOB_IDEAS.map(j => `<button type="button" data-idea="${esc(j)}">${esc(j)}</button>`).join("")}</div>
      <label>When<select name="due"><option value="${today}">Today</option><option value="${addDays(today, 1)}">Tomorrow</option>
        <option value="${addDays(today, 7)}">Within a week</option><option value="">Any time</option><option value="pick">Pick a date…</option></select></label>
      <input type="date" name="due_pick" hidden min="${today}">
      <label>Repeat<select name="repeat_days">${REPEATS.map(([d, l]) => `<option value="${d}">${l}</option>`).join("")}</select></label>
      <label>Where (optional)<select name="pasture_id">${pastureOptions(pre.pasture_id, "Anywhere / whole ranch")}</select></label>
      <label>Who (optional)<select name="assignee_id"><option value="">Anyone</option>${people.map(p => `<option value="${esc(p.user_id)}">${esc(p.name)}</option>`).join("")}</select></label>
      <label>Notes (optional)<textarea name="note" maxlength="1000">${esc(pre.note || "")}</textarea></label>
      <div class="row"><button type="submit" class="primary">Add job</button><button type="button" class="secondary" id="taskCancel">Cancel</button></div></form>`);
    const f = $("taskForm");
    f.querySelectorAll("[data-idea]").forEach(b => b.onclick = () => { f.title.value = b.dataset.idea; if (/water|cattle/i.test(b.dataset.idea)) f.repeat_days.value = "2"; });
    f.due.onchange = () => { f.due_pick.hidden = f.due.value !== "pick"; };
    $("taskCancel").onclick = closeSheet;
    f.onsubmit = e => {
      e.preventDefault();
      const due = f.due.value === "pick" ? f.due_pick.value : f.due.value;
      taskOp({op: "add", task_id: uid(), title: f.title.value.trim(), due_date: due || null, repeat_days: Number(f.repeat_days.value),
        pasture_id: f.pasture_id.value || null, assignee_id: f.assignee_id.value || null, note: f.note.value.trim() || null,
        lat: pre.lat ?? null, lon: pre.lon ?? null, source_id: pre.source_id || null});
      closeSheet(); toast("Job added."); if (!pre.source_id) show("todo");
    };
  }
  // "Make it a job" from a photo or a report
  window.__rangeiqMakeJob = (x, isPhoto) => {
    const top = topTag(x.tags);
    addTask({title: top ? (TAG[top].level === "info" ? `Check on ${top.toLowerCase()}` : `Deal with: ${top.toLowerCase()}`) : (isPhoto ? "Follow up on photo" : "Follow up"),
      pasture_id: x.pasture_id, note: x.text || x.note || "", lat: x.lat, lon: x.lon, source_id: x.client_id});
  };


  // ---------------------------------------------------------------- PLACES: tanks, ponds, blinds, feeders, gates... on the map
  async function loadPlaces() {
    try { setPlacesFromServer(await api("places")); } catch (e) { if (e.signin) throw e; }
  }
  function setPlacesFromServer(list) {
    places = list || [];
    for (const q of store.get("placeq", [])) {   // keep unsent changes on top
      places = places.filter(p => p.place_id !== q.place_id);
      if (!q.deleted) places.push(q);
    }
    store.set("places", places);
  }
  function placeChange(item) {
    item = {...item, updated_at: new Date().toISOString()};
    const q = store.get("placeq", []).filter(x => x.place_id !== item.place_id); q.push(item); store.set("placeq", q);
    places = places.filter(p => p.place_id !== item.place_id); if (!item.deleted) places.push({...item, created_by: item.created_by || (me && me.user_id),
      created_by_name: item.created_by_name || (me && me.name)});
    store.set("places", places); rerender(); syncAll();
  }
  function kindPicker(selected) {
    const groups = [["water", "💧 Water"], ["hunting", "🛖 Hunting"], ["ranch", "🏠 Ranch"], ["sensors", "📡 Sensors"]];
    return groups.map(([g, label]) => `<p class="dim small" style="margin-top:4px">${label}</p><div class="tagchips">${Object.entries(PLACE_KINDS)
      .filter(([, v]) => v[2] === g).map(([k, v]) => `<button type="button" data-kind="${k}" aria-pressed="${k === selected}">${v[1]} ${esc(v[0])}</button>`).join("")}</div>`).join("");
  }
  async function placePhoto() {                 // returns the queued photo's id, or null
    return new Promise(ok => {
      const input = $("camInput"); input.value = "";
      input.onchange = async e => {
        input.onchange = onCam;                    // back to the normal camera
        const file = e.target.files && e.target.files[0]; if (!file) return ok(null);
        try {
          const img = await loadImage(file);
          const [photo, thumb] = await Promise.all([toJpeg(img, 1600, 0.82), toJpeg(img, 360, 0.7)]); URL.revokeObjectURL(img.src);
          const client_id = uid(), fix = cam.fix && Date.now() - cam.fix.at < 120000 ? cam.fix : null;
          await idb.put({client_id, photo, thumb, meta: {client_id, taken_at: new Date().toISOString(), lat: fix ? fix.lat : null, lon: fix ? fix.lon : null,
            accuracy_m: fix ? fix.acc : null, heading_deg: null, pasture_id: null, tags: [], note: null, by: me && me.name, analysis: {}, flagged: false,
            place_id: placeDraft && placeDraft.place_id}});
          await loadPending(); ok(client_id);
        } catch (err) { toast("Couldn't use that photo: " + err.message); ok(null); }
      };
      input.click();
    });
  }
  let placeDraft = null;
  function addPlace(pre = {}) {
    startSensors();
    placeDraft = {place_id: uid(), kind: "water_tank", name: "", note: "", lat: null, lon: null, photo_id: null, ...pre};
    placeForm();
  }
  function placeForm() {
    const d = placeDraft, isNew = !places.some(p => p.place_id === d.place_id);
    const ph = d.photo_id && allPhotos().find(x => x.client_id === d.photo_id);
    openSheet(isNew ? "Add a place" : "Edit place", `<form class="form" id="placeForm"><div>${kindPicker(d.kind)}</div>
      <label>Name<input name="name" maxlength="80" required value="${esc(d.name)}" placeholder="${esc(PLACE_KINDS[d.kind][0])} by the north gate"></label>
      <div><p><b>Where</b></p><p class="dim" id="plWhere"></p>
        <div class="row"><button type="button" class="secondary" id="plGps">📍 Use where I'm standing</button>
        <button type="button" class="secondary" id="plTap">👆 Tap it on the map</button></div></div>
      <div class="row" style="align-items:center">${ph ? `<img class="placethumb" src="${esc(thumbOf(ph))}" alt="">` : ""}<button type="button" class="secondary" id="plPhoto">📷 ${ph ? "Change photo" : "Add a photo"}</button></div>
      <label id="plDevice" ${d.kind.startsWith("sensor_") ? "" : "hidden"}>Device ID (optional; on the sensor's label)<input name="device_id" maxlength="64" value="${esc(d.device_id || "")}" autocapitalize="characters"></label>
      <label>Notes (optional)<textarea name="note" maxlength="1000" placeholder="Holds about 2,000 gal · feeder set to 7 am">${esc(d.note || "")}</textarea></label>
      <div class="row"><button type="submit" class="primary">Save place</button><button type="button" class="secondary" id="plCancel">Cancel</button></div></form>`);
    const f = $("placeForm");
    const where = () => {
      const fx = cam.fix && Date.now() - cam.fix.at < 120000 ? cam.fix : null;
      $("plWhere").textContent = d.lat != null ? `Set: ${d.lat.toFixed(5)}, ${d.lon.toFixed(5)}${d.acc ? ` (±${d.acc} m)` : " (from the map)"}`
        : fx ? `Not set yet. Your phone is at ±${fx.acc} m.` : "Not set yet. Getting your location…";
    };
    where(); const t = setInterval(() => { if (!$("plWhere")) return clearInterval(t); where(); }, 1000);
    f.querySelectorAll("[data-kind]").forEach(b => b.onclick = () => {
      const was = PLACE_KINDS[d.kind][0]; d.kind = b.dataset.kind;
      f.querySelectorAll("[data-kind]").forEach(x => x.setAttribute("aria-pressed", String(x === b)));
      if (!f.name.value || f.name.value === was) f.name.value = PLACE_KINDS[d.kind][0];
      $("plDevice").hidden = !d.kind.startsWith("sensor_");
    });
    const keep = () => { d.name = f.name.value; d.note = f.note.value; d.device_id = f.device_id.value; };
    $("plGps").onclick = () => { const fx = cam.fix && Date.now() - cam.fix.at < 120000 ? cam.fix : null;
      if (!fx) { toast("No GPS fix yet. Try again in a moment, or tap it on the map."); return; } d.lat = fx.lat; d.lon = fx.lon; d.acc = fx.acc; where(); };
    $("plTap").onclick = () => { keep(); clearInterval(t); closeSheet();
      pickOnMap((lat, lon) => { if (lat != null) { d.lat = lat; d.lon = lon; d.acc = null; } placeForm(); }); };
    $("plPhoto").onclick = async () => { keep(); const id = await placePhoto(); if (id) { d.photo_id = id; if (d.lat == null && cam.fix) { d.lat = cam.fix.lat; d.lon = cam.fix.lon; d.acc = cam.fix.acc; } } placeForm(); };
    $("plCancel").onclick = () => { clearInterval(t); placeDraft = null; stopSensors(); closeSheet(); };
    f.onsubmit = e => {
      e.preventDefault(); keep();
      if (d.lat == null) { toast("Set where it is: use your location or tap it on the map."); return; }
      clearInterval(t); stopSensors();
      placeChange({place_id: d.place_id, kind: d.kind, name: d.name.trim() || PLACE_KINDS[d.kind][0], note: d.note.trim() || null,
        lat: d.lat, lon: d.lon, photo_id: d.photo_id || null, device_id: d.kind.startsWith("sensor_") ? (d.device_id || "").trim() || null : null});
      closeSheet(); toast("Place saved."); placeDraft = null;
    };
  }
  function openPlace(id) {
    const pl = places.find(x => x.place_id === id); if (!pl) return;
    const k = PLACE_KINDS[pl.kind] || PLACE_KINDS.other, ph = pl.photo_id && allPhotos().find(x => x.client_id === pl.photo_id);
    const canEdit = isOwner() || (me && pl.created_by === me.user_id);
    openSheet(`${k[1]} ${pl.name}`, `<p class="dim">${esc(k[0])}${pl.created_by_name ? " · added by " + esc(pl.created_by_name) : ""}</p>
      ${ph ? `<img class="photoimg" src="${esc(imageOf(ph))}" alt="Photo of ${esc(pl.name)}">` : ""}
      ${pl.note ? `<p>${esc(pl.note)}</p>` : ""}
      ${pl.kind.startsWith("sensor_") ? `<p class="dim small">${pl.device_id ? "Device " + esc(pl.device_id) + ". " : ""}Live readings will show here once sensors are connected to RangeIQ.</p>` : ""}
      <div class="row"><button type="button" class="secondary" id="plMap">Show on map</button>
        <button type="button" class="secondary" id="plJob">＋ Make it a job</button>
        ${canEdit ? `<button type="button" class="secondary" id="plEdit">Edit</button><button type="button" class="secondary" id="plDel">Delete</button>` : ""}</div>`);
    $("plMap").onclick = () => showOnMap(pl.lat, pl.lon);
    $("plJob").onclick = () => addTask({title: `Check ${pl.name}`, note: "", lat: pl.lat, lon: pl.lon, source_id: null,
      pasture_id: pastureAt(pl.lon, pl.lat)});
    if (canEdit) {
      $("plEdit").onclick = () => { placeDraft = {...pl}; startSensors(); placeForm(); };
      $("plDel").onclick = () => { if (confirm(`Delete ${pl.name}?`)) { placeChange({place_id: pl.place_id, deleted: true}); closeSheet(); } };
    }
  }

  // ---------------------------------------------------------------- sync (logs + photos + jobs + places)
  let syncing = false;
  async function syncAll(manual) {
    if (syncing) return;
    if (!navigator.onLine) { updateSyncPill(); if (manual) toast("No signal yet. Everything is safe on this phone."); return; }
    syncing = true;
    try {
      const q = store.get("queue", []);
      if (q.length) {
        const res = await api("logs", {method: "POST", body: JSON.stringify(q)});
        const done = new Set([...res.saved, ...res.errors.map(e => e.client_id)]);
        store.set("queue", store.get("queue", []).filter(e => !done.has(e.client_id)));
      }
      for (const rec of (await idb.all()) || []) {
        const fd = new FormData();
        fd.append("meta", JSON.stringify(rec.meta)); fd.append("photo", rec.photo, rec.client_id + ".jpg"); fd.append("thumb", rec.thumb, rec.client_id + "_t.jpg");
        try { await api("photos", {method: "POST", body: fd}); await idb.del(rec.client_id); }
        catch (e) { if (e.signin) throw e; if (e.status === 400 || e.status === 413) await idb.del(rec.client_id); else break; }
      }
      const tq = store.get("taskq", []);
      if (tq.length) {
        const res = await api("tasks", {method: "POST", body: JSON.stringify(tq)});
        const sent = new Set([...res.applied, ...res.errors.map(e => e.op_id)]);
        store.set("taskq", store.get("taskq", []).filter(o => !sent.has(o.op_id)));
        if (res.errors.length) toast(res.errors[0].error);
        setTasksFromServer(res.tasks);
      } else await loadTasks();
      const pq = store.get("placeq", []);
      if (pq.length) {
        const res = await api("places", {method: "POST", body: JSON.stringify(pq)});
        const sent = new Set([...res.saved, ...res.errors.map(e => e.place_id)]);
        store.set("placeq", store.get("placeq", []).filter(x => !sent.has(x.place_id)));
        if (res.errors.length) toast(res.errors[0].error);
        setPlacesFromServer(res.places);
      } else await loadPlaces();
      await loadPending();
      const [ph, lg] = await Promise.all([api("photos"), api("logs")]);
      photos = ph; serverLogs = lg; store.set("photos", photos); store.set("serverLogs", serverLogs);
    } catch (e) { if (e.signin) show("login"); }
    finally { syncing = false; rerender(); }
  }
  function updateSyncPill() {
    const n = store.get("queue", []).length + pending.length + store.get("taskq", []).length + store.get("placeq", []).length, p = $("syncPill");
    p.hidden = !n; p.textContent = n + " waiting to send";
  }
  $("syncPill").onclick = () => syncAll(true);

  // ---------------------------------------------------------------- sign in / join a crew
  document.querySelectorAll("[data-auth]").forEach(b => b.onclick = () => {
    document.querySelectorAll("[data-auth]").forEach(x => x.setAttribute("aria-selected", String(x === b)));
    $("loginForm").hidden = b.dataset.auth !== "signin"; $("joinForm").hidden = b.dataset.auth !== "join";
  });
  async function signedIn(who) {
    if (who.token) store.set("token", who.token);
    me = {name: who.name, ranch: who.ranch, role: who.role || "owner", workspace_id: who.workspace_id, ranches: who.ranches || []}; store.set("me", me);
    if (who.workspace_id) store.set("lastRanch", who.workspace_id);
    show("home"); await refresh(); syncAll();
  }
  // ---------------------------------------------------------------- switch between ranches (one login, several ranches)
  const unsent = () => store.get("queue", []).length + pending.length + store.get("taskq", []).length + store.get("placeq", []).length;
  async function switchRanch(workspaceId) {
    if (!me || workspaceId === me.workspace_id) { closeSheet(); return; }
    if (unsent()) { await syncAll(true); if (unsent()) { toast("Some photos or entries for this ranch haven't sent yet. Switch once they have."); return; } }
    try {
      const who = await api("switch", {method: "POST", body: JSON.stringify({workspace_id: workspaceId})});
      ["snapshot", "snapshotAt", "serverLogs", "photos", "tasks", "people", "places"].forEach(k => store.del(k));
      rawSnap = snap = null; photos = []; serverLogs = []; tasks = []; people = []; places = [];
      if (view3d) { view3d.dispose(); view3d = null; }
      closeSheet(); toast("Now on " + who.ranch); await signedIn(who);
    } catch (e) { if (e.signin) show("login"); else toast(navigator.onLine ? e.message : "Switching ranches needs signal."); }
  }
  function ranchPicker() {
    const rs = (me && me.ranches) || [];
    if (rs.length < 2) return;
    openSheet("Which ranch?", `<div class="tagpick">${rs.map(r => `<button type="button" class="${r.workspace_id === me.workspace_id ? "primary" : "secondary"}"
      data-ranch="${esc(r.workspace_id)}">${esc(r.name)}${r.role === "crew" ? " (crew)" : ""}</button>`).join("")}</div>`);
  }
  $("brandBtn").onclick = ranchPicker;
  document.addEventListener("click", e => { const r = e.target.closest("[data-ranch]"); if (r) switchRanch(r.dataset.ranch); });
  $("loginEmail").value = store.get("lastEmail", "");
  if (navigator.storage && navigator.storage.persist) navigator.storage.persist().catch(() => {});   // ask the phone not to clear the sign-in
  const iosBrowser = /iphone|ipad|ipod/i.test(navigator.userAgent) && !navigator.standalone;
  if (iosBrowser) $("loginTip").hidden = false;
  $("loginForm").onsubmit = async e => {
    e.preventDefault(); $("loginError").hidden = true;
    try { store.set("lastEmail", $("loginEmail").value.trim());
      await signedIn(await api("login", {method: "POST", body: JSON.stringify({email: $("loginEmail").value.trim(), password: $("loginPassword").value,
        ranch: store.get("lastRanch", "")})})); $("loginPassword").value = ""; }
    catch (err) { $("loginError").textContent = navigator.onLine ? err.message : "Signing in needs signal."; $("loginError").hidden = false; }
  };
  $("joinForm").onsubmit = async e => {
    e.preventDefault(); $("joinError").hidden = true;
    try { await signedIn(await api("join", {method: "POST", body: JSON.stringify({code: $("joinCode").value, name: $("joinName").value.trim(),
      email: $("joinEmail").value.trim(), password: $("joinPassword").value})})); $("joinPassword").value = ""; }
    catch (err) { $("joinError").textContent = navigator.onLine ? err.message : "Joining needs signal."; $("joinError").hidden = false; }
  };

  // ---------------------------------------------------------------- install / offline / start
  let deferred = null;
  addEventListener("beforeinstallprompt", e => { e.preventDefault(); deferred = e; $("installBtn").hidden = false; });
  $("installBtn").onclick = async () => { if (!deferred) return; deferred.prompt(); await deferred.userChoice; deferred = null; $("installBtn").hidden = true; };
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
  $("o-install").innerHTML = matchMedia("(display-mode: standalone)").matches || navigator.standalone ? "RangeIQ is on your home screen." : ios
    ? "In <b>Safari</b>, tap the <b>Share</b> button, then <b>Add to Home Screen</b>."
    : "Tap <b>Install</b> at the top, or the browser menu → <b>Install app</b>.";
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") { refresh(); syncAll(); } });

  (async function start() {
    await loadPending();
    updateSyncPill(); setBanner();
    show(store.get("token", null) || snap ? (location.hash.slice(1) || "home") : "login");
    refresh().then(() => syncAll());
  })();
})();
