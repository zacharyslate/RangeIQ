/* RangeIQ ranch icons: drawn for RangeIQ (no third-party artwork), one style, 48 x 48.
   RangeIcons.svg(key, size) -> "<svg ...>"; RangeIcons.has(key); RangeIcons.url(key) -> data: URL (for the 3D map). */
(function () {
  const INK = "#2e2318", WOOD = "#b07a45", STEEL = "#9aa6b0", STEEL_D = "#5f6b75", WATER = "#3b8fd1", GRASS = "#5f8f3a",
        DIRT = "#a8743f", RED = "#c0392b", CAMO = "#6d7b47", SKY = "#ffffff";
  const S = `fill="none" stroke="${INK}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"`;
  const bad = `<circle cx="38" cy="10" r="7.5" fill="${RED}" stroke="#fff" stroke-width="1.6"/><path d="M38 6v5M38 13.6v.4" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/>`;
  const ok = `<circle cx="38" cy="10" r="7.5" fill="#2e7d4f" stroke="#fff" stroke-width="1.6"/><path d="M34.5 10l2.6 2.6 4.6-5" ${S.replace(INK, "#fff")}/>`;
  const waves = `<path d="M14 30c2.5-2 5-2 7.5 0s5 2 7.5 0 5-2 7.5 0" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" opacity=".85"/>`;
  const signal = `<g fill="none" stroke="${INK}" stroke-width="2.2" stroke-linecap="round"><path d="M36 9a7 7 0 0 1 0 10"/><path d="M40 5.5a12 12 0 0 1 0 17"/></g>`;

  // ---- pieces reused by several icons
  const gate = (open) => open
    ? `<rect x="5" y="9" width="5" height="33" rx="1" fill="${WOOD}" stroke="${INK}" stroke-width="2"/>
       <g ${S} stroke="${STEEL_D}" stroke-width="2.6"><path d="M10 14l20 6M10 20l20 5.5M10 26l20 5M10 32l20 4.5M10 37l20 4"/><path d="M30 20v21"/><path d="M10 37l20-17"/></g>
       <path d="M38 42h6" ${S}/>`
    : `<rect x="4" y="9" width="5" height="33" rx="1" fill="${WOOD}" stroke="${INK}" stroke-width="2"/>
       <rect x="39" y="9" width="5" height="33" rx="1" fill="${WOOD}" stroke="${INK}" stroke-width="2"/>
       <g fill="none" stroke="${STEEL_D}" stroke-width="2.6" stroke-linecap="round"><path d="M10 15h28M10 20.5h28M10 26h28M10 31.5h28M10 37h28"/><path d="M10 15v22M38 15v22"/><path d="M10 37l28-22"/></g>
       <path d="M2 43h44" ${S}/>`;
  const cow = (fill = INK) => `<g fill="${fill}"><rect x="14" y="15" width="27" height="15" rx="6"/>
       <path d="M17 18L10 13.5 4.5 15.5 3.5 20.5 7.5 24.5 16 26z"/><path d="M10 14l3-4 2 5z"/><path d="M7 14.5l-3-3.5"/>
       <rect x="16" y="27" width="3.6" height="13" rx="1.4"/><rect x="22" y="27" width="3.6" height="13" rx="1.4"/>
       <rect x="31" y="27" width="3.6" height="13" rx="1.4"/><rect x="36.4" y="27" width="3.6" height="13" rx="1.4"/></g>
       <path d="M40.5 18c3 2 3.5 7 2.5 11" fill="none" stroke="${fill}" stroke-width="2" stroke-linecap="round"/>
       <path d="M8 13.5c-2-1.5-4-2-6-1.5" fill="none" stroke="${INK}" stroke-width="1.8" stroke-linecap="round"/>`;
  const trough = (level) => `<path d="M5 22h38l-4 16H9z" fill="${STEEL}" stroke="${INK}" stroke-width="2.4" stroke-linejoin="round"/>
       <path d="M9 ${22 + level}h30" stroke="${WATER}" stroke-width="${Math.max(2, 13 - level)}" stroke-linecap="butt" opacity=".95"/>
       <path d="M5 22h38" ${S}/><path d="M12 38v4M36 38v4" ${S}/>`;
  const windmill = `<g ${S}><path d="M24 17L15 44M24 17l9 27M17.5 36h13M19.5 28h9M15 44h18"/><path d="M17.5 36l11-8M19.5 28l9 8"/></g>
       <circle cx="24" cy="12" r="10" fill="#e9e3d6" stroke="${INK}" stroke-width="2.2"/>
       <g stroke="${INK}" stroke-width="1.6">${Array.from({length: 12}, (_, i) => { const a = i * Math.PI / 6; return `<path d="M${(24 + 3 * Math.cos(a)).toFixed(1)} ${(12 + 3 * Math.sin(a)).toFixed(1)}L${(24 + 9.5 * Math.cos(a)).toFixed(1)} ${(12 + 9.5 * Math.sin(a)).toFixed(1)}"/>`; }).join("")}</g>
       <circle cx="24" cy="12" r="2.4" fill="${INK}"/><path d="M26 12h15" ${S}/><path d="M38 7l7 2v7l-7 0z" fill="${STEEL}" stroke="${INK}" stroke-width="2" stroke-linejoin="round"/>`;
  const cattleGuard = `<rect x="10" y="2" width="28" height="44" fill="#d8c3a0"/>
       <rect x="9" y="11" width="30" height="26" rx="1.5" fill="#3a2c1e"/>
       ${[14, 18.5, 23, 27.5, 32].map(y => `<rect x="7" y="${y - 1.7}" width="34" height="3.4" rx="1.7" fill="#c9d2d9" stroke="${INK}" stroke-width="1.1"/>`).join("")}
       <g ${S}><path d="M5 9v30M43 9v30M5 9l-2-3M43 9l2-3M5 39l-2 3M43 39l2 3"/></g>`;
  const fence = (broken) => `<g ${S}><path d="M2 42h44"/></g>
       <rect x="6" y="12" width="4" height="30" rx="1" fill="${WOOD}" stroke="${INK}" stroke-width="1.8"/>
       <rect x="38" y="12" width="4" height="30" rx="1" fill="${WOOD}" stroke="${INK}" stroke-width="1.8"/>
       ${broken === "down"
         ? `<rect x="20" y="26" width="4" height="22" rx="1" transform="rotate(62 22 37)" fill="${WOOD}" stroke="${INK}" stroke-width="1.8"/>
            <g fill="none" stroke="${STEEL_D}" stroke-width="1.8" stroke-linecap="round"><path d="M10 17c6 10 12 16 19 21M10 25c5 7 10 11 16 14"/><path d="M38 17c-3 3-6 4-8 4M38 25c-3 2-5 3-7 3"/></g>`
         : `<rect x="22" y="12" width="4" height="30" rx="1" fill="${WOOD}" stroke="${INK}" stroke-width="1.8"/>
            <g fill="none" stroke="${STEEL_D}" stroke-width="1.8" stroke-linecap="round"><path d="M10 17h12M26 17h12M10 25h12M10 33h12M26 33h12"/>
            ${broken ? `<path d="M26 25h4M34 25h4" stroke="${RED}" stroke-width="2.2"/><path d="M30 25l2-3M34 25l-2 3" stroke="${RED}" stroke-width="2"/>` : `<path d="M26 25h12"/>`}</g>`}`;
  const road = `<path d="M18 2h12l12 44H6z" fill="#cdb48c" stroke="${INK}" stroke-width="2" stroke-linejoin="round"/><path d="M24 6v6M24 18v6M24 30v6M24 42v3" stroke="#fff" stroke-width="2"/>`;
  const hog = `<g fill="${INK}"><ellipse cx="26" cy="25" rx="15" ry="9.5"/><path d="M14 20L4 24.5 4.5 29 14 31z"/><rect x="2.5" y="24" width="3.2" height="6" rx="1.4" fill="#5a4636"/>
       <path d="M13 18l2.5-6 3.5 6z"/><rect x="15" y="30" width="3.6" height="10" rx="1.3"/><rect x="21" y="31" width="3.6" height="9" rx="1.3"/>
       <rect x="30" y="31" width="3.6" height="9" rx="1.3"/><rect x="35.5" y="30" width="3.6" height="10" rx="1.3"/>
       <path d="M17 16l2-3 2 3 2-3 2 3 2-3 2 3 2-3 2 3 2-3 2 3 2-2.5 1 3.5z"/></g>
       <path d="M6 30c1 2.5 3 3 4.5 2" fill="none" stroke="#f3ead9" stroke-width="1.6" stroke-linecap="round"/>
       <path d="M41 22c3-1 4 2 2 3s-1 3 1.5 2" fill="none" stroke="${INK}" stroke-width="1.6" stroke-linecap="round"/>`;
  const skull = `<path d="M24 14c-5 0-8 3-8 8 0 4 2 7 4 9v6c0 2 1.6 3 4 3s4-1 4-3v-6c2-2 4-5 4-9 0-5-3-8-8-8z" fill="#f4ecdc" stroke="${INK}" stroke-width="2.2" stroke-linejoin="round"/>
       <path d="M17 19C11 19 5 15 2 8c5 4 10 5 15 5M31 19c6 0 12-4 15-11-5 4-10 5-15 5" fill="#efe4cf" stroke="${INK}" stroke-width="2.2" stroke-linejoin="round"/>
       <ellipse cx="20.5" cy="23" rx="2.4" ry="3" fill="${INK}"/><ellipse cx="27.5" cy="23" rx="2.4" ry="3" fill="${INK}"/><path d="M22.5 34h3" ${S}/>`;
  const flame = `<path d="M24 4c3 7 11 11 11 22a11 11 0 0 1-22 0c0-6 3-9 5-12 1 4 3 6 5 6-1-6 0-11 1-16z" fill="#e8622c" stroke="${INK}" stroke-width="2.2" stroke-linejoin="round"/>
       <path d="M24 26c2 3 5 4 5 8a5 5 0 0 1-10 0c0-3 2-5 5-8z" fill="#ffc94a"/>`;
  const grassTuft = (h, color = GRASS) => `<g fill="none" stroke="${color}" stroke-width="2.6" stroke-linecap="round">
       ${[8, 13, 18, 23, 28, 33, 38].map((x, i) => `<path d="M${x} 42c${i % 2 ? 1 : -1} -${h * 0.5} ${i % 2 ? -1 : 2} -${h * 0.8} ${i % 2 ? 2 : -1} -${h}"/>`).join("")}</g><path d="M3 42h42" ${S}/>`;
  const drop = (fill = WATER) => `<path d="M24 5c6 9 13 16 13 24a13 13 0 0 1-26 0c0-8 7-15 13-24z" fill="${fill}" stroke="${INK}" stroke-width="2.2" stroke-linejoin="round"/><path d="M17 30a7 7 0 0 0 5 7" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" opacity=".8"/>`;
  const dirtTank = `<ellipse cx="24" cy="27" rx="21" ry="14" fill="${DIRT}" stroke="${INK}" stroke-width="2.2"/><ellipse cx="24" cy="28" rx="15" ry="9" fill="${WATER}"/>${waves}`;

  const I = {
    // ---------------- places
    water_tank: `<path d="M9 16h30v24c0 2-6.7 4-15 4s-15-2-15-4z" fill="${STEEL}" stroke="${INK}" stroke-width="2.2"/>
      <path d="M9 16l15-9 15 9" fill="#c5ced5" stroke="${INK}" stroke-width="2.2" stroke-linejoin="round"/>
      <g stroke="${STEEL_D}" stroke-width="1.6"><path d="M14 18v24M19 18v25M24 18v26M29 18v25M34 18v24"/></g>
      <path d="M9 16h30" ${S}/><path d="M33 22v16" stroke="${WATER}" stroke-width="3" stroke-linecap="round"/>`,
    trough: trough(4),
    pond: dirtTank,
    windmill: windmill,
    water_other: drop(),
    deer_blind: `<g ${S}><path d="M14 30l-3 14M34 30l3 14M14 30l20 0M12.5 37h23"/><path d="M38 44l-4-14"/></g>
      <path d="M10 9l14-5 14 5" fill="#4f5a32" stroke="${INK}" stroke-width="2.2" stroke-linejoin="round"/>
      <rect x="11" y="9" width="26" height="21" rx="2" fill="${CAMO}" stroke="${INK}" stroke-width="2.2"/>
      <rect x="15" y="14" width="18" height="4" rx="1" fill="${INK}"/><path d="M15 22l4 3 5-2 6 3" fill="none" stroke="#56633a" stroke-width="2"/>`,
    feeder: `<g ${S}><path d="M18 30L9 44M30 30l9 14M24 31v13"/></g>
      <rect x="15" y="4" width="18" height="24" rx="3" fill="${CAMO}" stroke="${INK}" stroke-width="2.2"/>
      <path d="M15 10h18M15 22h18" stroke="#4f5a32" stroke-width="2"/><rect x="19" y="28" width="10" height="5" rx="1" fill="${INK}"/>
      <g fill="#e8b93a">${[[12, 40], [17, 43], [31, 41], [36, 43], [22, 45], [27, 43]].map(([x, y]) => `<circle cx="${x}" cy="${y}" r="1.6"/>`).join("")}</g>`,
    game_camera: `<path d="M24 4v6M24 38v6" stroke="${DIRT}" stroke-width="8" stroke-linecap="round"/>
      <path d="M9 13h30M9 35h30" stroke="${INK}" stroke-width="2.4" stroke-linecap="round"/>
      <rect x="12" y="9" width="24" height="30" rx="5" fill="${CAMO}" stroke="${INK}" stroke-width="2.2"/>
      <circle cx="24" cy="25" r="6" fill="#1d1f22" stroke="${INK}" stroke-width="1.6"/><circle cx="24" cy="25" r="2.6" fill="#5d7ea6"/>
      <g fill="#b5262a">${[17, 21, 27, 31].map(x => `<circle cx="${x}" cy="14.5" r="1.3"/>`).join("")}</g>`,
    stand: `<g ${S}><path d="M14 44L22 10M24 44l6-34"/>${[38, 31, 24, 17].map(y => `<path d="M${15.5 + (44 - y) * 0.235 - 1.5} ${y}h${8 + 0.0}"/>`).join("")}</g>
      <rect x="18" y="5" width="16" height="5" rx="1" fill="${WOOD}" stroke="${INK}" stroke-width="2"/><path d="M30 5V1h-6" ${S}/><path d="M34 7.5h6l-3 7" ${S}/>`,
    gate: gate(false),
    cattle_guard: cattleGuard,
    pens: `<ellipse cx="24" cy="31" rx="21" ry="10" fill="#dcc49c"/>
      <path d="M4 20a20 8 0 0 1 40 0M4 27a20 8 0 0 1 40 0" fill="none" stroke="${STEEL}" stroke-width="2.2"/>
      <g fill="${INK}"><rect x="16" y="21" width="14" height="7.5" rx="3"/><path d="M17 23l-4.5-2-1 3.5 3.5 2.2z"/><rect x="17" y="27" width="2.2" height="6"/><rect x="27.5" y="27" width="2.2" height="6"/></g>
      <path d="M4 20a20 8 0 0 0 40 0M4 27a20 8 0 0 0 40 0" fill="none" stroke="${STEEL_D}" stroke-width="2.6"/>
      <g ${S}>${[-1, -0.75, -0.4, 0, 0.4, 0.75, 1].map(f => { const x = 24 + 20 * f, y = 20 + 8 * Math.sqrt(Math.max(0, 1 - f * f)); return `<path d="M${x.toFixed(1)} ${(y - 1).toFixed(1)}v11"/>`; }).join("")}</g>`,
    building: `<path d="M5 22l7-12h24l7 12v21H5z" fill="#a8402c" stroke="${INK}" stroke-width="2.2" stroke-linejoin="round"/>
      <path d="M5 22h38" ${S}/><path d="M12 10l-2 12M36 10l2 12" stroke="#7d2e1f" stroke-width="1.6"/>
      <rect x="17" y="27" width="14" height="16" fill="#f1e6d3" stroke="${INK}" stroke-width="2"/><path d="M17 27l14 16M31 27L17 43" stroke="${INK}" stroke-width="1.8"/>
      <rect x="21" y="15" width="6" height="5" fill="#f1e6d3" stroke="${INK}" stroke-width="1.6"/>`,
    mineral: `<ellipse cx="18" cy="22" rx="13" ry="4.5" fill="#23435f" stroke="${INK}" stroke-width="2"/><path d="M5 22v14c0 2.5 5.8 4.5 13 4.5S31 38.5 31 36V22" fill="#2f5d86" stroke="${INK}" stroke-width="2.2"/>
      <rect x="9" y="27" width="18" height="6" rx="1" fill="#e8b93a"/><path d="M5 22c0 2.5 5.8 4.5 13 4.5S31 24.5 31 22" ${S}/>
      <path d="M30 34l7-4 8 4-7 4z" fill="#ffffff" stroke="${INK}" stroke-width="1.8" stroke-linejoin="round"/><path d="M30 34v6l8 4v-6M38 44l7-4v-6" fill="#ece6dc" stroke="${INK}" stroke-width="1.8" stroke-linejoin="round"/>`,
    other: `<path d="M24 44S10 28 10 18a14 14 0 0 1 28 0c0 10-14 26-14 26z" fill="${RED}" stroke="${INK}" stroke-width="2.2"/><circle cx="24" cy="18" r="5" fill="#fff"/>`,
    sensor_rain: `<path d="M14 6h20l-5 9H19z" fill="#cfe3f3" stroke="${INK}" stroke-width="2" stroke-linejoin="round"/>
      <rect x="17" y="15" width="14" height="25" rx="2" fill="#e8f1f8" stroke="${INK}" stroke-width="2"/><rect x="18.5" y="28" width="11" height="10.5" fill="${WATER}"/>
      <g stroke="${INK}" stroke-width="1.3">${[19, 23, 27, 31, 35].map(y => `<path d="M17 ${y}h4"/>`).join("")}</g><path d="M24 40v5" ${S}/>${signal}`,
    sensor_water: `<path d="M6 18h28v22c0 2-6.3 4-14 4S6 42 6 40z" fill="${STEEL}" stroke="${INK}" stroke-width="2.2"/><path d="M8 30c4-3 8 3 12 0s8-3 12 0v10c0 1.5-5 3-12 3S8 41.5 8 40z" fill="${WATER}"/>
      <path d="M6 18h28" ${S}/><path d="M20 12v18" stroke="${INK}" stroke-width="2"/><rect x="16" y="7" width="8" height="5" rx="1" fill="#e8b93a" stroke="${INK}" stroke-width="1.6"/>${signal}`,
    sensor_soil: `<path d="M2 26h44v20H2z" fill="${DIRT}"/><path d="M2 26h44" ${S}/><g fill="#7a5229">${[[8, 33], [15, 40], [30, 36], [40, 42], [36, 30]].map(([x, y]) => `<circle cx="${x}" cy="${y}" r="1.6"/>`).join("")}</g>
      <rect x="19" y="8" width="10" height="12" rx="2" fill="#e8b93a" stroke="${INK}" stroke-width="2"/><path d="M21.5 20v20M26.5 20v20" stroke="${STEEL_D}" stroke-width="2.4" stroke-linecap="round"/>
      <path d="M8 22c0-3 2-5 4-6M10 22c1-2 2-3 4-3" stroke="${GRASS}" stroke-width="2" fill="none" stroke-linecap="round"/>${signal}`,
    sensor_weather: `<path d="M24 16v28M17 44h14" ${S}/><path d="M10 12h28" ${S}/>
      <g fill="#e8b93a" stroke="${INK}" stroke-width="1.8"><path d="M6 12a4 4 0 0 0 8 0z"/><path d="M34 12a4 4 0 0 0 8 0z"/></g><circle cx="24" cy="12" r="2.4" fill="${INK}"/>
      <path d="M24 24h12l3 3-3 3H24" fill="${STEEL}" stroke="${INK}" stroke-width="2" stroke-linejoin="round"/>${signal}`,
    sensor_other: `<path d="M24 20l-8 24M24 20l8 24M18.5 36h11M20.5 30h7" ${S}/><circle cx="24" cy="17" r="3.5" fill="${RED}" stroke="${INK}" stroke-width="1.8"/>
      <g fill="none" stroke="${INK}" stroke-width="2.2" stroke-linecap="round"><path d="M17 10a10 10 0 0 0 0 14M31 10a10 10 0 0 1 0 14M12 5a17 17 0 0 0 0 24M36 5a17 17 0 0 1 0 24"/></g>`,

    // ---------------- reports (tags)
    "Water low": `${trough(10)}<path d="M38 2v10m-3.5-3.5L38 12l3.5-3.5" stroke="${RED}" stroke-width="2.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`,
    "Trough or tank problem": `${trough(4)}<path d="M22 22l-2 5 3 2-2 6" stroke="${RED}" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>${bad}`,
    "Windmill or pump down": `${windmill}<path d="M30 30l12 12M42 30L30 42" stroke="${RED}" stroke-width="3.4" stroke-linecap="round"/>`,
    "Pipe or float leak": `<path d="M2 18h30a6 6 0 0 1 6 6v6" fill="none" stroke="${STEEL_D}" stroke-width="7" stroke-linecap="butt"/><path d="M2 18h30a6 6 0 0 1 6 6v6" fill="none" stroke="${STEEL}" stroke-width="3.5"/>
      <path d="M16 22c0 3 0 4 0 4" stroke="${WATER}" stroke-width="2.5" stroke-linecap="round"/><path d="M16 30c2.4 3 2.4 6 0 6s-2.4-3 0-6z" fill="${WATER}"/><path d="M38 34c2.4 3 2.4 6 0 6s-2.4-3 0-6z" fill="${WATER}"/>
      <path d="M10 44h28" stroke="${WATER}" stroke-width="2.4" stroke-linecap="round" opacity=".6"/>`,
    "Water OK": `${trough(1)}${ok}`,
    "Fence down": fence("down"),
    "Fence damaged": fence(true),
    "Gate open": `<rect x="4" y="9" width="5" height="33" rx="1" fill="${WOOD}" stroke="${INK}" stroke-width="2"/>
      <rect x="39" y="9" width="5" height="33" rx="1" fill="${WOOD}" stroke="${INK}" stroke-width="2"/>
      <g fill="none" stroke="${STEEL_D}" stroke-width="2.4" stroke-linecap="round"><path d="M9 14l9 4M9 20l9 3.5M9 26l9 3M9 32l9 2.5M9 37l9 2M18 18v21M9 37l9-19"/></g>
      <path d="M21 28h15m-4-4.5 4.5 4.5-4.5 4.5" fill="none" stroke="${RED}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M2 43h44" ${S}/>`,
    "Gate damaged": `${gate(false)}<path d="M18 26c3 2 5 2 8 0" stroke="${RED}" stroke-width="3" fill="none" stroke-linecap="round"/>${bad}`,
    "Cattle guard problem": `${cattleGuard}${bad}`,
    "Washed-out road": `${road}<path d="M10 20c6 2 8 6 12 6s8-6 14-4c-2 6-6 10-10 12s-10 0-12-4c-2-3-4-6-4-10z" fill="#7a5229" stroke="${INK}" stroke-width="1.8"/><path d="M14 27c4 2 8 3 14 0" stroke="${WATER}" stroke-width="2.4" fill="none" stroke-linecap="round"/>`,
    "Cattle out": `${cow()}<path d="M34 6h10m-3-3l3 3-3 3" stroke="${RED}" stroke-width="2.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`,
    "Sick or hurt animal": `${cow()}<circle cx="38" cy="9" r="7.5" fill="#fff" stroke="${RED}" stroke-width="2"/><path d="M38 5v8M34 9h8" stroke="${RED}" stroke-width="3" stroke-linecap="round"/>`,
    "Dead animal": skull,
    "Stray animal": `${cow("#6b4a2f")}<circle cx="38" cy="9" r="7.5" fill="#e8b93a" stroke="#fff" stroke-width="1.6"/><path d="M35.6 7a2.6 2.6 0 1 1 3.4 2.5c-.8.3-1 1-1 1.8M38 13.6v.3" fill="none" stroke="${INK}" stroke-width="2" stroke-linecap="round"/>`,
    "New calf": `<g transform="translate(6 8) scale(.78)">${cow("#8a5a33")}</g><path d="M37 8l1.2 2.6 2.8.4-2 2 .5 2.8-2.5-1.3-2.5 1.3.5-2.8-2-2 2.8-.4z" fill="#e8b93a" stroke="${INK}" stroke-width="1"/>`,
    "Feral hogs": hog,
    "Hog rooting damage": `${hog}<g fill="${DIRT}" stroke="${INK}" stroke-width="1.4"><path d="M2 46c2-5 6-5 8 0zM12 46c2-4 5-4 7 0zM34 46c2-5 6-5 8 0z"/></g>`,
    "Coyote or predator": `<path d="M8 44c0-8 3-14 7-18l-2-14 7 9c3-1 6-1 9 0l7-9-2 14c4 4 7 10 7 18" fill="#9b7653" stroke="${INK}" stroke-width="2.2" stroke-linejoin="round"/>
      <path d="M17 30c2 4 4 9 7 11 3-2 5-7 7-11" fill="#e6d3b5" stroke="${INK}" stroke-width="1.8" stroke-linejoin="round"/>
      <circle cx="19" cy="27" r="1.8" fill="${INK}"/><circle cx="29" cy="27" r="1.8" fill="${INK}"/><path d="M22.5 37h3l-1.5 2z" fill="${INK}"/>`,
    "Rattlesnake": `<path d="M10 40c-6-2-6-10 2-11h22c8-1 8-11 0-12H22c-6 0-6-8 0-9h8" fill="none" stroke="${INK}" stroke-width="7.2" stroke-linecap="round"/>
      <path d="M10 40c-6-2-6-10 2-11h22c8-1 8-11 0-12H22c-6 0-6-8 0-9h8" fill="none" stroke="#b08a52" stroke-width="4.4" stroke-linecap="round" stroke-dasharray="3 3"/>
      <ellipse cx="33" cy="8" rx="5" ry="3.6" fill="#8a6a3a" stroke="${INK}" stroke-width="1.8"/><circle cx="34.5" cy="7" r="1" fill="${INK}"/>
      <path d="M38 8h5l2-2M43 8l2 2" stroke="${RED}" stroke-width="1.6" fill="none" stroke-linecap="round"/>
      <g fill="#e2cfa3" stroke="${INK}" stroke-width="1.2"><ellipse cx="9" cy="40" rx="2.4" ry="2"/><ellipse cx="5.5" cy="41" rx="2" ry="1.7"/><ellipse cx="2.8" cy="41.8" rx="1.6" ry="1.4"/></g>`,
    "Deer": `<path d="M24 44c-4-1-6-10-6-17 0-4 3-7 6-7s6 3 6 7c0 7-2 16-6 17z" fill="#a0723f" stroke="${INK}" stroke-width="2.2" stroke-linejoin="round"/>
      <path d="M18 24c-5-1-8-4-9-7 4 0 7 1 9 3M30 24c5-1 8-4 9-7-4 0-7 1-9 3" fill="#a0723f" stroke="${INK}" stroke-width="2" stroke-linejoin="round"/>
      <g fill="none" stroke="#6b4a2f" stroke-width="2.6" stroke-linecap="round"><path d="M21 19C16 14 15 8 17 2M17 11l-5-3M16 6l-4-4M27 19c5-5 6-11 4-17M31 11l5-3M32 6l4-4"/></g>
      <circle cx="21" cy="29" r="1.7" fill="${INK}"/><circle cx="27" cy="29" r="1.7" fill="${INK}"/><ellipse cx="24" cy="41" rx="2.6" ry="2" fill="${INK}"/><path d="M21 34c2 1.5 4 1.5 6 0" stroke="#f3e7d1" stroke-width="2" fill="none"/>`,
    "Other wildlife": `<g fill="${INK}"><ellipse cx="24" cy="31" rx="9" ry="8"/><ellipse cx="12" cy="20" rx="4" ry="5.2" transform="rotate(-20 12 20)"/><ellipse cx="20" cy="12" rx="4" ry="5.4"/>
      <ellipse cx="29" cy="12" rx="4" ry="5.4"/><ellipse cx="37" cy="20" rx="4" ry="5.2" transform="rotate(20 37 20)"/></g>`,
    "Fire or smoke": flame,
    "Short or overgrazed grass": `<path d="M2 36h44v10H2z" fill="${DIRT}"/><path d="M2 36h44" ${S}/>
      <g stroke="#a49a4c" stroke-width="2.4" stroke-linecap="round">${[5, 9, 13, 21, 25, 33, 37, 41].map((x, i) => `<path d="M${x} 36v-${i % 3 ? 3 : 4.5}"/>`).join("")}</g>
      <g fill="${INK}" opacity=".85"><circle cx="17" cy="40" r="1.2"/><circle cx="29" cy="41" r="1.2"/></g>
      <path d="M8 14h32M8 14v6M40 14v6M14 14v3M20 14v3M26 14v3M32 14v3" stroke="${RED}" stroke-width="2" fill="none" stroke-linecap="round"/>
      <path d="M24 22v8m-3-3 3 3 3-3" stroke="${RED}" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`,
    "Weeds or brush": `<path d="M24 44V28M24 34l-7-6M24 31l8-7" stroke="#5a3d22" stroke-width="2.6" fill="none" stroke-linecap="round"/>
      <g fill="#6f8f3a" stroke="${INK}" stroke-width="1.8"><circle cx="15" cy="22" r="8"/><circle cx="33" cy="20" r="8"/><circle cx="24" cy="14" r="9"/></g>
      <g fill="#a5c06a">${[[13, 20], [22, 11], [31, 18], [26, 17], [17, 25]].map(([x, y]) => `<ellipse cx="${x}" cy="${y}" rx="2" ry="1"/>`).join("")}</g><path d="M6 44h36" ${S}/>`,
    "Poisonous plants": `<path d="M18 44V24" stroke="#4d7a2a" stroke-width="2.6" stroke-linecap="round"/>
      <g fill="#6f9a3a" stroke="${INK}" stroke-width="1.8"><path d="M18 30c-6 0-10-4-11-9 6 0 10 3 11 9zM18 26c6-1 9-5 9-10-6 1-9 4-9 10zM18 22c-3-3-3-8 0-12 3 4 3 9 0 12z"/></g>
      <circle cx="35" cy="33" r="10" fill="#fff" stroke="${INK}" stroke-width="1.8"/><path d="M30 31c0-3 2-5 5-5s5 2 5 5c0 2-1 3-2 3.5V37h-6v-2.5c-1-.5-2-1.5-2-3.5z" fill="${INK}"/>
      <circle cx="33" cy="31" r="1.3" fill="#fff"/><circle cx="37" cy="31" r="1.3" fill="#fff"/><path d="M6 44h24" ${S}/>`,
    "Erosion or washout": `<path d="M2 18c8 0 12 2 16 8s4 18 6 18 2-12 6-18 10-8 16-8v28H2z" fill="${DIRT}" stroke="${INK}" stroke-width="2" stroke-linejoin="round"/>
      <path d="M2 18h12M34 18h12" stroke="${GRASS}" stroke-width="3" stroke-linecap="round"/><path d="M21 36c1 3 2 6 3 8 1-2 2-5 3-8" fill="${WATER}"/><path d="M8 12l4 4M40 12l-4 4" stroke="${WATER}" stroke-width="2.2" stroke-linecap="round"/>`,
    "Good grass": `${grassTuft(22)}<g fill="#c9a94a">${[[13, 21], [23, 20], [33, 21]].map(([x, y]) => `<ellipse cx="${x}" cy="${y}" rx="1.6" ry="3.2"/>`).join("")}</g>`,

    // ---------------- USGS water map
    usgs_tank: dirtTank,
    usgs_pond: dirtTank,
    usgs_playa: `<ellipse cx="24" cy="26" rx="21" ry="15" fill="#e3cfa3" stroke="${INK}" stroke-width="2.2"/><g fill="none" stroke="#9c7b4a" stroke-width="1.8" stroke-linecap="round"><path d="M10 24l7 3 4-5 7 4 5-3 6 4M14 32l6-2 5 4 6-3M20 18l4 4"/></g>`,
    usgs_marsh: `${grassTuft(18, "#4f7f45")}<path d="M4 40c4-2 8-2 12 0s8 2 12 0 8-2 12 0" fill="none" stroke="${WATER}" stroke-width="2.4" stroke-linecap="round"/><g fill="#6d4a2b">${[[13, 22], [28, 18], [36, 24]].map(([x, y]) => `<rect x="${x - 1.6}" y="${y}" width="3.2" height="8" rx="1.6"/>`).join("")}</g>`,
    usgs_spring: `<g fill="#a69a8a" stroke="${INK}" stroke-width="1.8"><path d="M3 44l5-12 9-3 6 15z"/><path d="M27 44l3-14 10-3 6 17z"/></g><path d="M24 40c0-10-6-14-6-22M24 40c0-10 6-14 6-22" fill="none" stroke="${WATER}" stroke-width="2.6" stroke-linecap="round"/>
      <path d="M24 6c3 5 6 8 6 12a6 6 0 0 1-12 0c0-4 3-7 6-12z" fill="${WATER}" stroke="${INK}" stroke-width="1.8"/>`,
    usgs_well: `<rect x="18" y="20" width="12" height="22" fill="${STEEL}" stroke="${INK}" stroke-width="2"/><rect x="14" y="16" width="20" height="5" rx="1" fill="${STEEL_D}" stroke="${INK}" stroke-width="2"/>
      <path d="M30 26h8v14" fill="none" stroke="${STEEL_D}" stroke-width="3" stroke-linecap="round"/><path d="M38 41c2 3 2 5 0 5s-2-2 0-5z" fill="${WATER}"/><path d="M6 42h36" ${S}/><path d="M24 16V8h6" ${S}/>`,
    usgs_dam: `<path d="M2 20h18l6 24H2z" fill="${WATER}"/><path d="M14 18c6 0 10 2 14 6l8 20H20z" fill="${DIRT}" stroke="${INK}" stroke-width="2" stroke-linejoin="round"/>
      <path d="M14 18c6 0 10 2 14 6" stroke="${GRASS}" stroke-width="3" fill="none" stroke-linecap="round"/><path d="M4 28c3-2 6 2 9 0M4 35c3-2 6 2 9 0" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/><path d="M2 44h44" ${S}/>`,

    // ---------------- other pins and groups
    photo: `<rect x="5" y="14" width="38" height="26" rx="5" fill="#3a4450" stroke="${INK}" stroke-width="2"/><path d="M16 14l3-5h10l3 5" fill="#3a4450" stroke="${INK}" stroke-width="2" stroke-linejoin="round"/>
      <circle cx="24" cy="27" r="8.5" fill="#cfd8e0" stroke="${INK}" stroke-width="2"/><circle cx="24" cy="27" r="4" fill="${STEEL_D}"/><rect x="34" y="17" width="5" height="3" rx="1" fill="#e8b93a"/>`,
    note: `<rect x="9" y="7" width="30" height="37" rx="3" fill="#f6efe1" stroke="${INK}" stroke-width="2.2"/><rect x="17" y="4" width="14" height="7" rx="2" fill="${WOOD}" stroke="${INK}" stroke-width="2"/>
      <path d="M15 20h18M15 27h18M15 34h11" ${S}/>`,
    job: `<rect x="9" y="7" width="30" height="37" rx="3" fill="#f6efe1" stroke="${INK}" stroke-width="2.2"/><rect x="17" y="4" width="14" height="7" rx="2" fill="${WOOD}" stroke="${INK}" stroke-width="2"/>
      <path d="M14 21l3 3 5-6M14 33l3 3 5-6" fill="none" stroke="#2e7d4f" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M26 22h8M26 34h8" ${S}/>`,
    sos: `<circle cx="24" cy="24" r="21" fill="${RED}" stroke="#fff" stroke-width="2.4"/><text x="24" y="30.5" text-anchor="middle" font-family="system-ui, sans-serif" font-weight="900" font-size="16" fill="#fff">SOS</text>`,
    water: drop(),
    hunting: null, ranch: null, sensors: null, wildlife: null, problems: null,
    pastures: `<path d="M3 10l18-4 24 6-4 28-20 4L5 38z" fill="#d9c98f" stroke="${INK}" stroke-width="2.2" stroke-linejoin="round"/><path d="M21 6l-3 36M5 24l39 2" stroke="${INK}" stroke-width="2" stroke-dasharray="3 3"/>`,
    flags: `<path d="M12 44V5" stroke="${INK}" stroke-width="2.6" stroke-linecap="round"/><path d="M13 6h22l-6 7 6 7H13z" fill="#e0a21b" stroke="${INK}" stroke-width="2" stroke-linejoin="round"/>`,
    usgs: dirtTank, jobs: null, photos: null,
  };
  I.hunting = I.deer_blind; I.ranch = I.gate; I.sensors = I.sensor_other; I.wildlife = I.Deer; I.problems = I["Fence down"];
  I.jobs = I.job; I.photos = I.photo;
  // Group headings of the report picker
  I["group:Water"] = drop(); I["group:Fences, gates & roads"] = I["Fence damaged"]; I["group:Livestock"] = cow(); I["group:Wildlife"] = I.Deer; I["group:Grass & land"] = I["Good grass"];

  const cache = {};
  window.RangeIcons = {
    has: k => !!I[k],
    keys: () => Object.keys(I),
    svg(k, size = 24, cls = "ricon") {
      const body = I[k]; if (!body) return "";
      return `<svg class="${cls}" viewBox="0 0 48 48" width="${size}" height="${size}" aria-hidden="true" focusable="false">${body}</svg>`;
    },
    url(k) {                                    // data: URL for drawing on a canvas (3D map pins)
      if (cache[k]) return cache[k];
      const body = I[k]; if (!body) return null;
      return (cache[k] = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="96" height="96">${body}</svg>`));
    },
  };
})();
