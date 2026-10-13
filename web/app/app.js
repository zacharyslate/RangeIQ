/* RangeIQ phone app. Plain JavaScript, no build step (same approach as the Marfa Lights app).
   Data flow: the nightly worker writes a ranch snapshot -> GET /api/snapshot -> cached on the phone.
   Logs are saved on the phone first, then POSTed (idempotent by client_id) whenever there is signal. */
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const API = new URL("../api/", location.href).href;
  const store = {
    get(k, d) { try { const v = localStorage.getItem("riq." + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem("riq." + k, JSON.stringify(v)); } catch (e) {} },
    del(k) { try { localStorage.removeItem("riq." + k); } catch (e) {} }
  };
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const STATUS = {
    good: {word: "Good", icon: "✓"}, watch: {word: "Watch", icon: "!"}, act: {word: "Act", icon: "!!"}, unknown: {word: "No data", icon: "?"}
  };
  const LEVEL = {ok: "✓", watch: "!", concern: "!!", unavailable: "–"};
  let snap = store.get("snapshot", null);
  let snapFetchedAt = store.get("snapshotAt", null);
  let currentPasture = null;
  let map = null, mapLayers = [];

  // ---------------------------------------------------------------- helpers
  function uid() { return (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2)).slice(0, 36); }
  function when(iso, withTime = true) {
    if (!iso) return "";
    if (/^\d{4}$/.test(String(iso))) return String(iso);
    const d = new Date(iso.length === 10 ? iso + "T12:00:00" : iso); if (isNaN(d)) return iso;
    const today = new Date(); const yday = new Date(Date.now() - 864e5);
    const same = (a, b) => a.toDateString() === b.toDateString();
    const t = d.toLocaleTimeString([], {hour: "numeric", minute: "2-digit"});
    if (same(d, today)) return withTime ? "today " + t : "today";
    if (same(d, yday)) return withTime ? "yesterday " + t : "yesterday";
    return d.toLocaleDateString([], {month: "short", day: "numeric", year: d.getFullYear() === today.getFullYear() ? undefined : "numeric"}) + (withTime ? " " + t : "");
  }
  function toast(msg) { const t = document.createElement("div"); t.className = "toast"; t.textContent = msg; document.body.appendChild(t); setTimeout(() => t.remove(), 2600); }
  async function api(path, opts = {}) {
    const res = await fetch(API + path, {credentials: "same-origin", headers: {"Content-Type": "application/json"}, ...opts});
    if (res.status === 401) { const e = new Error("signin"); e.signin = true; throw e; }
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || ("HTTP " + res.status));
    return res.json();
  }
  function pastureName(id) { const p = (snap && snap.pastures || []).find(x => x.id === id); return p ? p.name : (id || ""); }

  // ---------------------------------------------------------------- views
  const TABS = ["today", "pastures", "log", "more"];
  function show(view) {
    let tab = view;
    if (view.startsWith("log-")) { tab = "log"; setTimeout(() => openLog(view.slice(4)), 50); }
    if (view.startsWith("pasture-")) { currentPasture = decodeURIComponent(view.slice(8)); tab = "pasture"; }
    if (!["login", "pasture", ...TABS].includes(tab)) tab = "today";
    document.querySelectorAll(".view").forEach(v => { v.hidden = v.id !== "v-" + tab; });
    document.querySelectorAll(".tabs [data-tab]").forEach(b => b.toggleAttribute("aria-current", b.dataset.tab === (tab === "pasture" ? "pastures" : tab)));
    document.querySelectorAll(".tabs [data-tab]").forEach(b => { if (b.hasAttribute("aria-current")) b.setAttribute("aria-current", "page"); });
    document.querySelector(".tabs").hidden = tab === "login";
    const hash = tab === "pasture" ? "pasture-" + encodeURIComponent(currentPasture) : tab;
    if (location.hash !== "#" + hash && !view.startsWith("log-")) history.replaceState(null, "", "#" + hash);
    if (tab === "pastures") renderPastures();
    if (tab === "pasture") renderPasture();
    if (tab === "log") renderLog();
    if (tab === "more") renderMore();
    window.scrollTo(0, 0);
  }
  document.querySelectorAll(".tabs [data-tab]").forEach(b => b.onclick = () => show(b.dataset.tab));
  document.addEventListener("click", e => {
    const go = e.target.closest("[data-go]"); if (go) { show(go.dataset.go); return; }
    const p = e.target.closest("[data-pasture]"); if (p) { show("pasture-" + encodeURIComponent(p.dataset.pasture)); return; }
    const lg = e.target.closest("[data-log]"); if (lg) openLog(lg.dataset.log, lg.dataset.here ? currentPasture : null);
  });
  window.addEventListener("hashchange", () => show(location.hash.slice(1)));

  // ---------------------------------------------------------------- banner (offline / demo / stale)
  function setBanner() {
    const b = $("banner"); const parts = []; let demo = false;
    if (snap && snap.demo) { demo = true; parts.push("Demo data: RangeIQ couldn't reach its data sources, so these numbers are examples, not your ranch."); }
    if (!navigator.onLine) parts.push("No signal. Showing what was saved " + (snapFetchedAt ? when(snapFetchedAt) : "earlier") + ".");
    b.hidden = !parts.length; b.textContent = parts.join(" "); b.classList.toggle("demo", demo && navigator.onLine);
  }
  window.addEventListener("online", () => { setBanner(); refresh(); sync(); });
  window.addEventListener("offline", setBanner);

  // ---------------------------------------------------------------- data
  async function refresh() {
    try {
      const data = await api("snapshot");
      if (data.pending) { snap = null; $("t-sum").textContent = data.message; renderToday(); return; }
      snap = data; snapFetchedAt = new Date().toISOString();
      store.set("snapshot", snap); store.set("snapshotAt", snapFetchedAt);
      renderToday();
      api("logs").then(rows => { store.set("serverLogs", rows); if (!$("v-log").hidden) renderLog(); if (!$("v-pasture").hidden) renderPasture(); }).catch(() => {});
    } catch (e) {
      if (e.signin) { show("login"); return; }
      renderToday();  // offline or server down: keep showing the saved snapshot
    } finally { setBanner(); }
  }

  // ---------------------------------------------------------------- TODAY
  function prow(p) {
    const s = STATUS[p.status] || STATUS.unknown;
    return `<li><button type="button" class="prow ${esc(p.status)}" data-pasture="${esc(p.id)}">
      <span class="badge" aria-hidden="true">${s.icon}</span><b>${esc(p.name)} <span class="chip ${esc(p.status)}">${s.word}</span></b>
      <span class="go" aria-hidden="true">›</span><span class="why">${esc(p.headline)}</span></button></li>`;
  }
  function renderToday() {
    if (!snap) { $("t-pastures").innerHTML = ""; $("t-counts").innerHTML = ""; $("t-weather").innerHTML = "<p class='dim'>Waiting for the first nightly update…</p>"; $("t-rain").hidden = true; return; }
    $("brandName").textContent = snap.ranch.name || "RangeIQ";
    $("t-updated").textContent = "Updated " + when(snap.generated_at);
    $("t-h").textContent = snap.ranch.name;
    const c = snap.counts || {};
    const n = snap.pastures.length;
    $("t-sum").textContent = c.act ? `${c.act} of ${n} pasture${n > 1 ? "s" : ""} need${c.act === 1 ? "s" : ""} action.` :
      c.watch ? `${c.watch} of ${n} pasture${n > 1 ? "s" : ""} to watch.` :
      c.good === n ? "No warning signs in any pasture." : "Not enough data yet to judge every pasture.";
    $("t-counts").innerHTML = ["act", "watch", "good", "unknown"].filter(k => c[k]).map(k => `<span class="chip ${k}">${STATUS[k].icon} ${c[k]} ${STATUS[k].word}</span>`).join("");
    $("t-pastures").innerHTML = snap.pastures.map(prow).join("");

    // alerts
    const al = snap.alerts || [];
    $("t-alerts").hidden = !al.length;
    $("t-alerts").innerHTML = "<h2>Weather alerts</h2>" + al.map(a => `<div class="alert ${/severe|extreme/i.test(a.severity) ? "" : "minor"}">
      <b>${esc(a.event)}</b><span class="dim">${esc(a.headline)}</span>${a.what_it_means ? `<span>${esc(a.what_it_means)}</span>` : ""}
      ${a.expires ? `<span class="src">Until ${esc(when(a.expires))}</span>` : ""}</div>`).join("");

    // weather
    const w = snap.weather;
    if (!w) { $("t-weather").innerHTML = "<h2>Weather</h2><p class='dim'>Forecast not available right now.</p>"; }
    else {
      const fc = (w.forecast || []).slice(0, innerWidth < 560 ? 5 : 7).map(d => {
        const day = new Date(d.date + "T12:00:00").toLocaleDateString([], {weekday: "short"});
        return `<div><span>${esc(day)}</span><b>${d.high_f ?? "–"}°</b><span class="dim">${d.low_f ?? "–"}°</span><span class="src">${d.rain_chance_pct != null ? d.rain_chance_pct + "%" : ""}</span></div>`;
      }).join("");
      $("t-weather").innerHTML = `<h2>Weather</h2><div class="tiles">
        <div class="tile"><span>Now</span><b>${w.temp_f ?? "–"}°F</b><span>${esc(w.label || "")}</span></div>
        <div class="tile"><span>Wind</span><b>${w.wind_mph ?? "–"} mph</b><span>${w.gust_mph ? "gusts " + w.gust_mph + " mph" : ""} ${esc(w.wind_dir || "")}</span></div></div>
        <div class="fc" aria-label="Seven day forecast: day, high, low, chance of rain">${fc}</div>`;
    }

    // rain vs normal
    const r = snap.rain;
    $("t-rain").hidden = false;
    if (!r || r.rain_90d_in == null) { $("t-rain").innerHTML = "<h2>Rain</h2><p class='dim'>Rain history not available right now.</p>"; }
    else {
      const pct = r.normal_90d_in ? Math.round(100 * r.rain_90d_in / r.normal_90d_in) : null;
      const fill = pct == null ? 0 : Math.min(100, pct / 1.5);
      $("t-rain").innerHTML = `<h2>Rain, last 90 days</h2>
        <p><b style="font-size:1.4rem">${r.rain_90d_in.toFixed(1)} in</b> ${pct != null ? `· <b>${pct}%</b> of normal (${r.normal_90d_in.toFixed(1)} in)` : ""}</p>
        ${pct != null ? `<div class="meter" role="img" aria-label="${pct} percent of normal"><i style="width:${fill}%"></i><s style="left:${100 / 1.5}%"></s></div>` : ""}
        <p class="dim">Last 30 days: ${r.rain_30d_in != null ? r.rain_30d_in.toFixed(2) + " in" : "–"}.</p>
        <p class="src">Gridded rain estimate through ${esc(when(r.as_of, false))}, compared with the same 90 days in the past ${r.normal_years} years. Your own gauge readings are in the Log.</p>`;
    }

    // fire
    const f = snap.fire;
    $("t-fire").hidden = !f;
    if (f) $("t-fire").innerHTML = `<h2>Fire danger: ${esc(f.level)}</h2>${(f.drivers || []).length ? `<p>${f.drivers.map(esc).join(" · ")}</p>` : "<p class='dim'>No fire-weather triggers in the forecast data.</p>"}
      ${(f.actions || []).map(a => `<p class="dim">${esc(a)}</p>`).join("")}<p class="src">Follow official burn bans and fire warnings.</p>`;
  }

  // ---------------------------------------------------------------- PASTURES (map loads only when needed)
  function loadLeaflet() {
    if (window.L) return Promise.resolve();
    return new Promise((ok, fail) => {
      const css = document.createElement("link"); css.rel = "stylesheet"; css.href = "vendor/leaflet/leaflet.css"; document.head.appendChild(css);
      const s = document.createElement("script"); s.src = "vendor/leaflet/leaflet.js"; s.onload = ok; s.onerror = fail; document.head.appendChild(s);
    });
  }
  const COLOR = {good: "#1f6b3a", watch: "#c98a00", act: "#c0392b", unknown: "#777"};
  async function renderPastures() {
    $("p-list").innerHTML = snap ? snap.pastures.map(prow).join("") : "<li class='dim'>No pastures yet.</li>";
    if (!snap || !snap.pastures.length) return;
    try { await loadLeaflet(); } catch (e) { $("map").innerHTML = "<p class='dim' style='padding:16px'>Map couldn't load. The list below still works.</p>"; return; }
    if (!map) {
      map = L.map("map", {zoomControl: true, attributionControl: true});
      L.tileLayer("https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}",
        {maxZoom: 19, maxNativeZoom: 16, attribution: "USGS The National Map"}).addTo(map);
    }
    mapLayers.forEach(l => l.remove()); mapLayers = [];
    const all = [];
    snap.pastures.forEach(p => {
      const latlngs = p.outline.map(([lon, lat]) => [lat, lon]); all.push(...latlngs);
      const poly = L.polygon(latlngs, {color: "#fff", weight: 2, fillColor: COLOR[p.status] || "#777", fillOpacity: .45})
        .on("click", () => show("pasture-" + encodeURIComponent(p.id)));
      poly.bindTooltip(`${esc(p.name)} · ${STATUS[p.status] ? STATUS[p.status].word : ""}`, {permanent: snap.pastures.length <= 12, direction: "center", className: "maplabel"});
      poly.addTo(map); mapLayers.push(poly);
    });
    map.invalidateSize(); map.fitBounds(all, {padding: [20, 20]});
  }

  // ---------------------------------------------------------------- PASTURE DETAIL
  function logLine(l) {
    const what = l.kind === "move" ? `Moved cattle${l.from_pasture_id ? " from " + esc(pastureName(l.from_pasture_id)) : ""} to ${esc(pastureName(l.pasture_id))}${l.head ? " (" + esc(l.head) + " head)" : ""}`
      : l.kind === "rain" ? `Rain gauge: <b>${Number(l.inches).toFixed(2)} in</b>${l.pasture_id ? " at " + esc(pastureName(l.pasture_id)) : ""}`
      : `${esc(l.text)}${l.pasture_id ? ` <span class="dim">(${esc(pastureName(l.pasture_id))})</span>` : ""}`;
    return `<li><span>${what}${l._pending ? ' <span class="pending">waiting to send</span>' : ""}</span><span class="when">${esc(when(l.logged_at))}</span></li>`;
  }
  function allLogs() {
    const q = store.get("queue", []).map(l => ({...l, _pending: true}));
    const s = store.get("serverLogs", []).filter(l => !q.some(x => x.client_id === l.client_id));
    return [...q, ...s].sort((a, b) => (b.logged_at || "").localeCompare(a.logged_at || ""));
  }
  function renderPasture() {
    const p = snap && snap.pastures.find(x => x.id === currentPasture);
    if (!p) { show("pastures"); return; }
    const s = STATUS[p.status] || STATUS.unknown;
    $("d-h").textContent = p.name;
    $("d-acres").textContent = p.acres != null ? p.acres + " acres" : "";
    $("d-status").innerHTML = `<span class="chip ${esc(p.status)}">${s.icon} ${s.word}</span> <span class="dim">${esc(p.headline)}</span>`;
    $("d-signals").innerHTML = "<h2>What the data says</h2>" + p.signals.map(g => `<div class="sig"><span class="lv ${esc(g.level)}" aria-label="${esc(g.level)}">${LEVEL[g.level] || "?"}</span>
      <b>${esc(g.label)}</b><span>${esc(g.text)}</span><span class="src">${g.source ? esc(g.source) : ""}${g.as_of ? " · " + esc(when(g.as_of, false)) : ""}</span></div>`).join("");
    const t = p.terrain;
    $("d-terrain").innerHTML = "<h2>Lay of the land</h2>" + (t ? `<div class="tiles">
      <div class="tile"><span>Elevation</span><b>${t.elev_min_ft}–${t.elev_max_ft} ft</b><span>${t.relief_ft} ft of relief</span></div>
      <div class="tile"><span>Average slope</span><b>${t.mean_slope_pct}%</b><span>${t.steep_share_pct ? t.steep_share_pct + "% steeper than 30%" : "no steep ground"}</span></div>
      <div class="tile"><span>Mostly faces</span><b>${esc(t.faces || "–")}</b><span>direction of slope</span></div>
      <div class="tile"><span>Easy grazing</span><b>${t.slope_adjusted_acres ?? "–"} ac</b><span>after slope (Holechek)</span></div></div>
      <p class="src">From USGS lidar (3DEP). Slope adjustment is a rule of thumb; check it against where cattle actually graze.</p>`
      : "<p class='dim'>Terrain not available right now.</p>");
    const logs = allLogs().filter(l => l.pasture_id === p.id || l.from_pasture_id === p.id).slice(0, 8);
    $("d-logs").innerHTML = "<h2>Recent log</h2>" + (logs.length ? `<ul class="loglist">${logs.map(logLine).join("")}</ul>` : "<p class='dim'>Nothing logged here yet.</p>");
  }

  // ---------------------------------------------------------------- LOG (offline-first queue)
  function pastureOptions(selected, blank) {
    const opts = (snap && snap.pastures || []).map(p => `<option value="${esc(p.id)}" ${p.id === selected ? "selected" : ""}>${esc(p.name)}</option>`).join("");
    return (blank ? `<option value="">${esc(blank)}</option>` : "") + opts;
  }
  function closeSheet() { $("sheet").hidden = true; $("sheetBack").hidden = true; }
  $("sheetBack").onclick = closeSheet;
  function openLog(kind, here) {
    const f = $("sheetForm");
    const now = new Date(); const local = new Date(now - now.getTimezoneOffset() * 6e4).toISOString().slice(0, 16);
    const whenField = `<label>When<input type="datetime-local" name="logged_at" value="${local}"></label>`;
    if (kind === "move") {
      $("sheetTitle").textContent = "Moved cattle";
      f.innerHTML = `<label>Moved into<select name="pasture_id" required>${pastureOptions(here, "Choose pasture")}</select></label>
        <label>Moved out of<select name="from_pasture_id">${pastureOptions(null, "— not from a pasture —")}</select></label>
        <label>Head (optional)<input type="number" name="head" inputmode="numeric" min="0" step="1"></label>${whenField}`;
    } else if (kind === "rain") {
      $("sheetTitle").textContent = "Rain gauge reading";
      f.innerHTML = `<label>Inches<input type="number" name="inches" inputmode="decimal" min="0" max="20" step="0.01" required></label>
        <div class="quick">${[0.1, 0.25, 0.5, 1].map(v => `<button type="button" data-in="${v}">${v.toFixed(2)}</button>`).join("")}</div>
        <label>Gauge location (optional)<select name="pasture_id">${pastureOptions(here, "— ranch gauge —")}</select></label>${whenField}`;
      f.querySelectorAll("[data-in]").forEach(b => b.onclick = () => { f.inches.value = b.dataset.in; });
    } else {
      kind = "note";
      $("sheetTitle").textContent = "Note";
      f.innerHTML = `<label>What did you see?<textarea name="text" required maxlength="2000" placeholder="Trough float stuck, grass grazed short by the gate, gap in the fence…"></textarea></label>
        <label>Pasture (optional)<select name="pasture_id">${pastureOptions(here, "— whole ranch —")}</select></label>${whenField}`;
    }
    f.insertAdjacentHTML("beforeend", `<div class="row"><button type="submit" class="primary">Save</button><button type="button" class="secondary" id="sheetCancel">Cancel</button></div>`);
    $("sheetCancel").onclick = closeSheet;
    f.onsubmit = e => {
      e.preventDefault();
      const data = Object.fromEntries(new FormData(f).entries());
      const entry = {client_id: uid(), kind, logged_at: new Date(data.logged_at || Date.now()).toISOString()};
      if (data.pasture_id) entry.pasture_id = data.pasture_id;
      if (kind === "move") { if (data.from_pasture_id && data.from_pasture_id !== data.pasture_id) entry.from_pasture_id = data.from_pasture_id; if (data.head) entry.head = Number(data.head); }
      if (kind === "rain") entry.inches = Number(data.inches);
      if (kind === "note") entry.text = data.text.trim();
      const q = store.get("queue", []); q.push(entry); store.set("queue", q);
      closeSheet(); toast(navigator.onLine ? "Saved. Sending…" : "Saved on this phone. It will send when there's signal.");
      updateSyncPill(); renderLog(); if (!$("v-pasture").hidden) renderPasture();
      sync();
    };
    $("sheet").hidden = false; $("sheetBack").hidden = false;
    setTimeout(() => { const first = f.querySelector("select,input,textarea"); if (first) first.focus(); }, 60);
  }
  let syncing = false;
  async function sync() {
    const q = store.get("queue", []);
    if (!q.length || syncing || !navigator.onLine) { updateSyncPill(); return; }
    syncing = true;
    try {
      const res = await api("logs", {method: "POST", body: JSON.stringify(q)});
      const done = new Set([...res.saved, ...res.errors.map(e => e.client_id)]);  // rejected entries won't succeed on retry
      store.set("queue", store.get("queue", []).filter(e => !done.has(e.client_id)));
      if (res.errors.length) toast("Some entries couldn't be saved: " + res.errors[0].error);
      store.set("serverLogs", await api("logs"));
    } catch (e) { if (e.signin) show("login"); }
    finally { syncing = false; updateSyncPill(); if (!$("v-log").hidden) renderLog(); }
  }
  function updateSyncPill() {
    const n = store.get("queue", []).length; const p = $("syncPill");
    p.hidden = !n; p.textContent = n + " waiting to send"; p.classList.add("warn");
  }
  $("syncPill").onclick = () => { sync(); toast(navigator.onLine ? "Sending…" : "No signal yet. Your entries are safe on this phone."); };
  function renderLog() {
    const q = store.get("queue", []);
    $("g-queue").hidden = !q.length;
    $("g-queue").innerHTML = `<p><b>${q.length} entr${q.length === 1 ? "y" : "ies"} waiting to send.</b> They're safe on this phone and will send automatically when there's signal.</p><button type="button" class="secondary" id="syncNow">Send now</button>`;
    if ($("syncNow")) $("syncNow").onclick = sync;
    const logs = allLogs().slice(0, 40);
    $("g-list").innerHTML = logs.length ? logs.map(logLine).join("") : "<li class='dim'>Nothing logged yet. Use the buttons above.</li>";
  }

  // ---------------------------------------------------------------- MORE
  function renderMore() {
    const src = (snap && snap.sources) || [];
    $("m-sources").innerHTML = src.length ? src.map(s => `<li><span><b>${esc(s.name)}</b><br><span class="${s.live ? "ok-txt" : "no-txt"}">${s.live ? (s.stale ? "Working (older copy)" : "Working") : s.demo ? "Demo values" : "Not available"}</span></span>
      <span class="when">${s.as_of ? "data through<br>" + esc(when(s.as_of, false)) : ""}</span></li>`).join("") : "<li class='dim'>No data yet.</li>";
    api("me").then(m => { $("m-account").textContent = `Signed in as ${m.name} (${m.email}) for ${m.ranch}.`; }).catch(() => {
      $("m-account").textContent = navigator.onLine ? "" : "Account details need signal.";
    });
  }
  $("logoutBtn").onclick = async () => {
    if (store.get("queue", []).length && !confirm("You have entries that haven't been sent yet. Sign out anyway? They stay on this phone.")) return;
    try { await api("logout", {method: "POST"}); } catch (e) {}
    store.del("snapshot"); store.del("snapshotAt"); store.del("serverLogs"); snap = null; show("login");
  };
  function setSize(v) { document.documentElement.style.setProperty("--scale", v); store.set("scale", v);
    document.querySelectorAll("[data-size]").forEach(b => b.setAttribute("aria-pressed", b.dataset.size === String(v))); }
  document.querySelectorAll("[data-size]").forEach(b => b.onclick = () => setSize(b.dataset.size));
  setSize(store.get("scale", "1"));

  // ---------------------------------------------------------------- sign in
  $("loginForm").onsubmit = async e => {
    e.preventDefault(); $("loginError").hidden = true;
    try {
      await api("login", {method: "POST", body: JSON.stringify({email: $("loginEmail").value.trim(), password: $("loginPassword").value})});
      $("loginPassword").value = ""; show("today"); await refresh(); sync();
    } catch (err) { $("loginError").textContent = navigator.onLine ? (err.message === "signin" ? "That email and password don't match." : err.message) : "Signing in needs signal."; $("loginError").hidden = false; }
  };

  // ---------------------------------------------------------------- install / offline
  let deferred = null;
  window.addEventListener("beforeinstallprompt", e => { e.preventDefault(); deferred = e; $("installBtn").hidden = false; });
  $("installBtn").onclick = async () => { if (!deferred) return; deferred.prompt(); await deferred.userChoice; deferred = null; $("installBtn").hidden = true; };
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
  const standalone = matchMedia("(display-mode: standalone)").matches || navigator.standalone;
  $("m-install").innerHTML = standalone ? "RangeIQ is installed on this phone." : ios
    ? "On iPhone: open this page in <b>Safari</b>, tap the <b>Share</b> button, then <b>Add to Home Screen</b>."
    : "On Android: tap <b>Install</b> at the top, or open the browser menu and choose <b>Install app</b> / <b>Add to Home screen</b>.";
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") { refresh(); sync(); } });

  // ---------------------------------------------------------------- start
  updateSyncPill(); renderToday(); setBanner();
  show(location.hash.slice(1) || "today");
  refresh().then(sync);
})();
