/* Sun and moon for the ranch: sunrise/sunset, first/last light, moon phase, moonrise/moonset.
   Worked out on the phone (no signal needed) with the low-precision formulas from J. Meeus, Astronomical
   Algorithms (2nd ed., 1998) and the Astronomy Answers articles by Aa. Kollmann (aa.quae.nl), the same
   approach as the SunCalc library. Accurate to about a minute for sun times and a few minutes for the moon,
   which is plenty for planning a day. */
(function (root) {
  "use strict";
  const PI = Math.PI, rad = PI / 180, dayMs = 864e5, J1970 = 2440588, J2000 = 2451545, e = rad * 23.4397;
  const toJulian = d => d.valueOf() / dayMs - 0.5 + J1970;
  const fromJulian = j => new Date((j + 0.5 - J1970) * dayMs);
  const toDays = d => toJulian(d) - J2000;
  const rightAscension = (l, b) => Math.atan2(Math.sin(l) * Math.cos(e) - Math.tan(b) * Math.sin(e), Math.cos(l));
  const declination = (l, b) => Math.asin(Math.sin(b) * Math.cos(e) + Math.cos(b) * Math.sin(e) * Math.sin(l));
  const altitude = (H, phi, dec) => Math.asin(Math.sin(phi) * Math.sin(dec) + Math.cos(phi) * Math.cos(dec) * Math.cos(H));
  const siderealTime = (d, lw) => rad * (280.16 + 360.9856235 * d) - lw;
  const solarMeanAnomaly = d => rad * (357.5291 + 0.98560028 * d);
  const eclipticLongitude = M => M + rad * (1.9148 * Math.sin(M) + 0.02 * Math.sin(2 * M) + 0.0003 * Math.sin(3 * M)) + rad * 102.9372 + PI;
  function sunCoords(d) { const L = eclipticLongitude(solarMeanAnomaly(d)); return {dec: declination(L, 0), ra: rightAscension(L, 0)}; }

  // --- sun times
  const J0 = 0.0009;
  const julianCycle = (d, lw) => Math.round(d - J0 - lw / (2 * PI));
  const approxTransit = (Ht, lw, n) => J0 + (Ht + lw) / (2 * PI) + n;
  const solarTransitJ = (ds, M, L) => J2000 + ds + 0.0053 * Math.sin(M) - 0.0069 * Math.sin(2 * L);
  const hourAngle = (h, phi, d) => Math.acos((Math.sin(h) - Math.sin(phi) * Math.sin(d)) / (Math.cos(phi) * Math.cos(d)));
  function sunTimes(date, lat, lng) {
    const lw = rad * -lng, phi = rad * lat, d = toDays(date), n = julianCycle(d, lw), ds = approxTransit(0, lw, n);
    const M = solarMeanAnomaly(ds), L = eclipticLongitude(M), dec = declination(L, 0), Jnoon = solarTransitJ(ds, M, L);
    const at = deg => {
      const w = hourAngle(deg * rad, phi, dec);
      if (isNaN(w)) return [null, null];
      const Jset = solarTransitJ(approxTransit(w, lw, n), M, L);
      return [fromJulian(Jnoon - (Jset - Jnoon)), fromJulian(Jset)];
    };
    const [sunrise, sunset] = at(-0.833), [dawn, dusk] = at(-6);
    return {solarNoon: fromJulian(Jnoon), sunrise, sunset, dawn, dusk};
  }

  // --- moon
  function moonCoords(d) {
    const L = rad * (218.316 + 13.176396 * d), M = rad * (134.963 + 13.064993 * d), F = rad * (93.272 + 13.229350 * d);
    const l = L + rad * 6.289 * Math.sin(M), b = rad * 5.128 * Math.sin(F), dt = 385001 - 20905 * Math.cos(M);
    return {ra: rightAscension(l, b), dec: declination(l, b), dist: dt};
  }
  function moonAltitude(date, lat, lng) {
    const lw = rad * -lng, phi = rad * lat, d = toDays(date), c = moonCoords(d), H = siderealTime(d, lw) - c.ra;
    // Geocentric altitude. Rise/set uses +0.133 deg, which already allows for parallax (~0.95 deg), refraction (0.57 deg)
    // and the moon's half-width (0.25 deg), so no separate refraction term here.
    return altitude(H, phi, c.dec);
  }
  function moonIllumination(date) {
    const d = toDays(date), s = sunCoords(d), m = moonCoords(d), sdist = 149598000;
    const phi = Math.acos(Math.sin(s.dec) * Math.sin(m.dec) + Math.cos(s.dec) * Math.cos(m.dec) * Math.cos(s.ra - m.ra));
    const inc = Math.atan2(sdist * Math.sin(phi), m.dist - sdist * Math.cos(phi));
    const angle = Math.atan2(Math.cos(s.dec) * Math.sin(s.ra - m.ra),
      Math.sin(s.dec) * Math.cos(m.dec) - Math.cos(s.dec) * Math.sin(m.dec) * Math.cos(s.ra - m.ra));
    return {fraction: (1 + Math.cos(inc)) / 2, phase: 0.5 + 0.5 * inc * (angle < 0 ? -1 : 1) / PI};
  }
  /* Moonrise/moonset during the 24 hours after `start`, scanning hour by hour and fitting a parabola (Montenbruck & Pfleger). */
  function moonTimes(start, lat, lng) {
    const hc = 0.133 * rad, at = hrs => new Date(start.valueOf() + hrs * 36e5);
    let h0 = moonAltitude(start, lat, lng) - hc, rise = null, set = null, ye = 0;
    for (let i = 1; i <= 24; i += 2) {
      const h1 = moonAltitude(at(i), lat, lng) - hc, h2 = moonAltitude(at(i + 1), lat, lng) - hc;
      const a = (h0 + h2) / 2 - h1, b = (h2 - h0) / 2, xe = -b / (2 * a);
      ye = (a * xe + b) * xe + h1;
      const disc = b * b - 4 * a * h1;
      let roots = 0, x1 = 0, x2 = 0;
      if (disc >= 0) {
        const dx = Math.sqrt(disc) / (Math.abs(a) * 2);
        x1 = xe - dx; x2 = xe + dx;
        if (Math.abs(x1) <= 1) roots++;
        if (Math.abs(x2) <= 1) roots++;
        if (x1 < -1) x1 = x2;
      }
      if (roots === 1) { if (h0 < 0) rise = i + x1; else set = i + x1; }
      else if (roots === 2) { rise = i + (ye < 0 ? x2 : x1); set = i + (ye < 0 ? x1 : x2); }
      if (rise !== null && set !== null) break;
      h0 = h2;
    }
    const out = {};
    if (rise !== null) out.rise = at(rise);
    if (set !== null) out.set = at(set);
    if (rise === null && set === null) out[ye > 0 ? "alwaysUp" : "alwaysDown"] = true;
    return out;
  }
  function phaseName(p) {
    const names = [[0.0339, "New moon", "🌑"], [0.2161, "Waxing crescent", "🌒"], [0.2839, "First quarter", "🌓"], [0.4661, "Waxing gibbous", "🌔"],
      [0.5339, "Full moon", "🌕"], [0.7161, "Waning gibbous", "🌖"], [0.7839, "Last quarter", "🌗"], [0.9661, "Waning crescent", "🌘"], [1.01, "New moon", "🌑"]];
    const hit = names.find(([edge]) => p < edge);
    return {name: hit[1], icon: hit[2]};
  }
  /* Next new or full moon after `date`, found by stepping a day at a time and then refining (good to ~1 h). */
  function nextPhase(date, target) {
    const dist = t => { const p = moonIllumination(t).phase; let x = p - target; if (x < 0) x += 1; return x; };
    let t = new Date(date.valueOf()), prev = dist(t);
    for (let i = 0; i < 31; i++) {
      const n = new Date(t.valueOf() + dayMs), cur = dist(n);
      if (cur < prev) {                             // passed the target between t and n (distance wraps from ~1 to ~0)
        let lo = t.valueOf(), hi = n.valueOf();
        for (let k = 0; k < 24; k++) { const mid = (lo + hi) / 2; if (dist(new Date(mid)) > 0.5) lo = mid; else hi = mid; }
        return new Date(hi);
      }
      t = n; prev = cur;
    }
    return null;
  }
  const api = {sunTimes, moonTimes, moonIllumination, phaseName, nextPhase, moonAltitude};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.RangeSky = api;
})(typeof window !== "undefined" ? window : this);
