/* RangeIQ in English or Spanish.
   English is the source text. es.js holds the Spanish for each English string, plus patterns for text that comes
   from the server or outside services with numbers or names inside (pasture status, weather, alerts).
     t("Take photo")                         -> the app's own words
     t("{n} photos", {n: 3})                 -> with values filled in ({name} placeholders)
     tx("Fence down reported by Juan.")      -> server or outside text: exact match, then the patterns
   A missing Spanish entry shows the English, and is listed in RangeI18n.missing (the browser tests check it is empty).
   The language is the phone's (Spanish if the phone is set to Spanish) until someone picks one under More. */
(function () {
  "use strict";
  const ES = window.RANGEIQ_ES || {t: {}, patterns: []};
  const norm = s => String(s).replace(/\s+/g, " ").trim();
  const dict = {};
  for (const k in ES.t || {}) dict[norm(k)] = ES.t[k];
  const lower = {};
  for (const k in dict) lower[k.toLowerCase()] = dict[k];
  const pats = (ES.patterns || []).map(p => ({re: new RegExp(p.re), es: p.es, g: p.g || ""}));

  let lang = null;
  try { lang = JSON.parse(localStorage.getItem("riq.lang") || "null"); } catch (e) { lang = null; }
  if (lang !== "en" && lang !== "es") {
    const prefs = navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || "en"];
    lang = /^es\b/i.test(prefs[0] || "") ? "es" : "en";
  }
  document.documentElement.lang = lang;
  const missing = new Set();

  const fill = (s, vars) => vars ? s.replace(/\{(\w+)\}/g, (m, k) => (Object.prototype.hasOwnProperty.call(vars, k) ? String(vars[k]) : m)) : s;
  function t(key, vars) {
    if (lang !== "es") return fill(key, vars);
    const v = dict[norm(key)];
    if (v == null) { missing.add(key); return fill(key, vars); }
    return fill(v, vars);
  }
  // Text from the server or an outside service. Exact match first (ignoring case: "water ok" finds "Water OK"),
  // then the patterns, where {1} is a captured part as is and {t1} is a captured part translated too. Patterns can
  // belong to a group (e.g. "wx" for weather words) so they only apply to that kind of text.
  function tx(text, group) {
    if (lang !== "es" || text == null || text === "") return text;
    const k = norm(text);
    if (!/[A-Za-z]/.test(k)) return text;
    if (group) {                                   // a group's own words first ("wx:Rain" -> "lluvia")
      const gk = group + ":" + k;
      if (dict[gk] != null) return dict[gk];
      if (lower[gk.toLowerCase()] != null) return lower[gk.toLowerCase()];
    }
    if (dict[k] != null) return dict[k];
    const lo = lower[k.toLowerCase()];
    if (lo != null) return /^[a-z]/.test(k) ? lo.charAt(0).toLowerCase() + lo.slice(1) : lo;
    for (const p of pats) {
      if (p.g !== (group || "")) continue;
      const m = k.match(p.re);
      if (m) return p.es.replace(/\{(t?)(\d)\}/g, (_, tr, n) => { const g = m[Number(n)] == null ? "" : m[Number(n)]; return tr ? tx(g, group) : g; });
    }
    missing.add("tx: " + k);
    return text;
  }
  // The page's fixed words (index.html), once at start. Elements marked data-i18n are translated whole (their inner
  // HTML is the key); everything else text node by text node, plus aria-label, placeholder, title and alt.
  function apply(root) {
    if (lang !== "es") return;
    root.querySelectorAll("[data-i18n]").forEach(el => {
      const k = norm(el.innerHTML), v = dict[k];
      if (v != null) el.innerHTML = v; else missing.add(k);
    });
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT), nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(n => {
      if (!n.parentElement || n.parentElement.closest("[data-i18n],script,style")) return;
      const k = norm(n.nodeValue);
      if (!k || !/[A-Za-z]{2}/.test(k)) return;
      const v = dict[k];
      if (v == null) { missing.add(k); return; }
      const lead = n.nodeValue.match(/^\s*/)[0], trail = n.nodeValue.match(/\s*$/)[0];
      n.nodeValue = lead + v + trail;
    });
    root.querySelectorAll("[aria-label],[placeholder],[title],[alt]").forEach(el => {
      for (const a of ["aria-label", "placeholder", "title", "alt"]) {
        const val = el.getAttribute(a);
        if (!val || !/[A-Za-z]{2}/.test(val)) continue;
        const v = dict[norm(val)];
        if (v != null) el.setAttribute(a, v); else missing.add(val);
      }
    });
  }
  function setLang(l) {
    try { localStorage.setItem("riq.lang", JSON.stringify(l === "es" ? "es" : "en")); } catch (e) {}
    location.reload();
  }
  window.RangeI18n = {lang, t, tx, apply, setLang, missing, locale: lang === "es" ? "es-US" : undefined};
})();
