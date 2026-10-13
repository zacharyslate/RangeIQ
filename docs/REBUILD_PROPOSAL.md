# RangeIQ Rebuild Proposal

Prepared 2026-10-13. This builds on `UX_REVIEW.md` (what users see) and `DATA_UPGRADE_PLAN.md` (what the numbers are built from).

## Recommendation in one paragraph

**Keep the engine and rebuild RangeIQ as a phone-first installable web app (PWA).** The domain package (`src/ranch_ai`: about 14,000 lines with 101 tests, data clients, RAP/NDVI, soils, drought, terrain) is the valuable part and mostly sound, so it stays in Python. What changes is everything around it:
- A **nightly worker** computes each pasture's status ahead of time.
- A **small read-only API** serves the results.
- A **phone web app** opens from your URL, installs to the Home Screen, and keeps working with weak or no signal.

The current Streamlit app is kept as a **desktop admin console** for you, not for ranchers. No big-bang rewrite: each phase ships on its own.

## Who we're designing for

| Fact | Source | What it means for the design |
|---|---|---|
| Average U.S. producer age is **58.1** (2022 Census of Agriculture) | [Seed World / USDA NASS](https://www.seedworld.com/us/2024/02/15/usda-releases-2022-census-of-agriculture-data/) | Large text, high contrast, few choices per screen, no jargon |
| **82 %** of farms have a smartphone; 69 % a desktop or laptop | [USDA 2023 Technology Use, via Benton](https://www.benton.org/headlines/2023-technology-use-farm-computer-usage-and-ownership-report) | Design for the phone first |
| **75 %** of internet-connected farms use a cellular data plan; **15 %** of farms have no internet at all | same | Pages must be light and work on weak or no signal |

**Design rules that follow:**
- Each screen answers one rancher question:
  - "Is anything wrong today?"
  - "How's the grass in each pasture?"
  - "Where are my cattle, and when did I move them?"
  - "How much rain did we get?"
- Words before numbers. Say "Grass below normal for October", not "NDVI anomaly −0.08".
- Show where every number comes from and its date, for example "Rain: PRISM, through Oct 11".
- Logging a move, a rain-gauge reading or a note takes no more than **2 taps and 1 number**.
- Never show simulated data as if it were real. Demo data lives only on a clearly labeled sample ranch.

## What's wrong with the current architecture (measured)

| Finding | Evidence | Consequence |
|---|---|---|
| Work happens while the user waits | `run_mvp_pipeline` runs inside the page script. With 30 pastures and **mock** providers it takes 9.8 s; live providers add network time and timeouts. | Slow first load. A provider outage becomes a slow page. |
| Every tab computes on every click | Streamlit docs: by default "all tab content is computed and sent to the frontend regardless of which tab is selected" ([st.tabs](https://docs.streamlit.io/develop/api-reference/layout/st.tabs)) | Typing one note reruns weather, the model, maps and terrain. |
| Heavy baseline on a 1 GB server | Importing the app's libraries uses ~210 MB RSS before any work. Terrain for 10,000 ac peaked at **969 MB**; this is now fixed to ~394 MB. | Little headroom for concurrent users, so an out-of-memory crash is a real risk. |
| Live connection required | Streamlit keeps a websocket open per session | Weak rural cellular means dropped sessions and lost unsaved input. |
| One huge UI file, no UI tests | `app/dashboard.py`: 4,309 lines, ~640 lines of inline CSS, 115 `session_state` references; 0 dashboard tests | Every change risks breaking something unseen (e.g., the header rendered below every tab). |
| No backups | DigitalOcean shows "long running Droplets without Automated Backups enabled". User accounts live in SQLite on that droplet. | One disk problem loses every account and log. **Turn on backups today.** |

## Why an installable web app (PWA), not an app-store app

| | Installable web app (chosen) | Native app-store app |
|---|---|---|
| Install | Open the URL, then "Add to Home Screen" | App Store / Google Play |
| Cost and gatekeeping | None | Apple Developer Program **$99/yr** ([Apple](https://developer.apple.com/programs/)) plus review for each update |
| Codebase | One, for iPhone and Android | One with React Native/Expo, plus store builds |
| Offline | App shell and last results cached; logs queued on the phone and synced when the app is next opened with signal | Stronger background sync |
| Push notifications (later) | iPhone supports web push for Home Screen web apps since iOS 16.4 ([WebKit](https://webkit.org/?p=13878)) | Full support |
| iPhone storage | Safari's 7-day storage cap does not apply to apps added to the Home Screen. This is WebKit's stated intent, not a formal guarantee ([analysis](https://searchengineland.com/what-safaris-7-day-cap-on-script-writeable-storage-means-for-pwa-developers-332519)). | Persistent |

**Mitigation for the storage caveat:** the server is the source of truth, and every queued log is pushed the moment there's signal. The phone only ever holds unsynced entries and a cache.

The app can be wrapped for the stores later (e.g., with Capacitor) if ranchers ask, reusing the same code.

## Target architecture

```
 nightly (systemd timer)            always-on, light               the rancher's phone
┌───────────────────────────┐   ┌──────────────────────────┐   ┌──────────────────────────────┐
│ Worker (Python, ranch_ai) │   │ API (FastAPI, read +     │   │ PWA (installable web app)    │
│ • weather, alerts, rain,  │   │   log endpoints only)    │   │ • Today • Pastures • Log     │
│   drought, NDVI, RAP,     │──▶│ • no heavy imports       │◀─▶│ • Settings                   │
│   terrain                 │DB │ • JSON, gzip, cache hdrs │   │ • service worker: offline     │
│ • pasture status + reason │   │ • terrain tiles (later)  │   │   shell + last results       │
│ • source + date per input │   └──────────────────────────┘   │ • IndexedDB: queued logs      │
└───────────────────────────┘                                  └──────────────────────────────┘
          SQLite (+ DigitalOcean backups)     Streamlit admin console (you only): diagnostics, models
```

- **Heavy work only in the worker.** The API never imports scikit-learn, rasterio or Streamlit, so it stays small on the 1 GB droplet and answers fast. It never calls an outside data source while a rancher waits.
- **Results table:** one row per pasture per day with status (Good / Watch / Act), a plain-words reason, the input values, the **source and date** of each input, and a "stale" flag when a source failed.
- **Offline logging:** moves, rain-gauge readings, notes and photos are written to the phone first (IndexedDB) and synced to the API with a client-generated ID, so double-sends can't create duplicates.
- **Map:** MapLibre GL with the USGS NAIP imagery the app already uses, plus pasture outlines. Later, 3D terrain in the same map from the cached lidar DEM (served as terrain tiles), replacing the heavy Plotly 3D view on phones.
- **Front end:** a small Svelte + TypeScript app built with Vite; this is swappable. The aim is the smallest, most readable code that gives offline support and a fast first load on cellular. Caddy, which you already use, serves it.
- **Login:** keep the existing account system; sessions last for weeks so you aren't logging in at the gate.

## The phone app (4 screens)

1. **Today:** one big row per pasture (🟢 Good / 🟡 Watch / 🔴 Act, with a one-line reason), rain in the last 7 and 30 days vs. normal, active NWS alerts, fire danger, and an "Updated 5:10 am" timestamp.
2. **Pastures:** map plus a list. Tapping a pasture shows its card: grass trend in words with a small chart, rain, slope and terrain summary, last move, and days rested.
3. **Log:** big buttons for **Moved cattle · Rain gauge · Note/photo**. Each takes 2 taps and works with no signal; a "3 waiting to sync" badge shows anything unsynced.
4. **Settings:** ranch, pastures (upload, or draw on the map), herds. Everything else lives in the admin console.

**Phone-specific design rules:**
- Text of at least 17 px and tap targets of at least 48 px, usable with gloves.
- High-contrast "sunlight" theme by default.
- First load under about 300 KB before map tiles, so it works on one bar of LTE.

## Phases

| Phase | Scope | Rough effort | Exit test |
|---|---|---|---|
| **0 (this week)** | Turn on DigitalOcean backups; merge PR #1 after the live terrain check; pin Streamlit | hours | Backups visible; current app unchanged |
| **1: Engine → results** | Worker + SQLite results table + read-only FastAPI; status rules from observed data only; tests | ~1–2 weeks | Nightly run fills results for Caja Caliente; API answers in < 300 ms with every outside source down |
| **2: Phone app** | PWA with Today, Pastures, Log (offline queue), Settings; install on your iPhone | ~3–4 weeks | Installed on your phone; logging a move in airplane mode syncs when signal returns; usable one-handed outdoors |
| **3: Terrain + polish** | 3D terrain in the phone map; Streamlit trimmed to an admin console; optional alerts later | ~1–2 weeks | Terrain loads on cellular in < 5 s |

## Risks and honest caveats

- **The status calls are only as good as the model.** Today the forage score is trained on a synthetic target (see `DATA_UPGRADE_PLAN.md`). A cleaner app will make those numbers *more* believable, so fix the target before ranchers rely on the Good/Watch/Act colors. Until then, base status only on observed inputs (rain vs. normal, NDVI vs. normal, RAP trend, drought, days rested) with simple, explainable rules.
- **A rewrite drops behavior that existing tests don't cover.** Phase 1 keeps `src/ranch_ai` and its tests unchanged and adds smoke tests for every page.
- **iPhone background sync is limited for web apps.** Queued logs sync when the app is next opened with signal, not silently in the background. That's acceptable for logging, but say so in the UI.
- **New front-end code to maintain.** Keep the PWA small: 4 screens, no design framework, and end-to-end tests with Playwright, which is already available.
- **Effort ranges are estimates** for one developer working with Claude. Validate them against Phase 1 actuals.

## Decisions (2026-10-13)

1. **Audience: your own land first.** Optimize for Caja Caliente, but don't hard-code it.
2. **Platform: phone first, delivered as an installable web app (PWA).** Python stays for the engine, worker and API. Streamlit becomes your desktop admin console only.
3. **Alerts: none yet.** The worker still records results with dates, so alerts or web push can be added later without rework.
