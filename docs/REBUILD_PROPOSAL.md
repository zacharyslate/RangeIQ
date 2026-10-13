# RangeIQ Rebuild Proposal

Prepared 2026-10-13. This builds on `UX_REVIEW.md` (what users see) and `DATA_UPGRADE_PLAN.md` (what the numbers are built from).

## Recommendation in one paragraph

**Keep the engine, rebuild the shell, and change when the work happens.** The domain package (`src/ranch_ai`: about 14,000 lines with 101 tests, data clients, RAP/NDVI, soils, drought, terrain) is the valuable part and mostly sound. The problems are in the app around it. A 4,309-line Streamlit script recomputes everything while the rancher waits, has no UI tests, and puts developer tooling in front of users. Rebuild in two phases:

1. **Make it robust.** A scheduled job computes each ranch's results ahead of time. The app only reads and displays them, on 4 simple screens.
2. **Make it rancher-native.** Add a phone-first view that tolerates bad signal, plus a weekly text or email brief that pushes the answers to the rancher. Only start this after 3–5 real ranchers have tried Phase 1.

No big-bang rewrite.

## Who we're designing for

| Fact | Source | What it means for the design |
|---|---|---|
| Average U.S. producer age is **58.1** (2022 Census of Agriculture) | [Seed World / USDA NASS](https://www.seedworld.com/us/2024/02/15/usda-releases-2022-census-of-agriculture-data/) | Large text, high contrast, few choices per screen, no jargon |
| **82 %** of farms have a smartphone; 69 % a desktop or laptop | [USDA 2023 Technology Use, via Benton](https://www.benton.org/headlines/2023-technology-use-farm-computer-usage-and-ownership-report) | Design for the phone first |
| **75 %** of internet-connected farms use a cellular data plan; **15 %** of farms have no internet at all | same | Pages must be light and work on weak signal; push key info by text or email |

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

## Target architecture

```
          nightly / hourly                       on request
┌──────────────────────────────┐        ┌──────────────────────────┐
│ Worker (cron/systemd timer)  │        │ App (reads only)         │
│  • pull weather/alerts/      │        │  • Today  • Pastures     │
│    drought/NDVI/RAP/terrain  │ writes │  • Log    • Settings     │
│  • compute pasture status    │──────▶ │                          │
│  • record source + date      │  DB    │ Weekly brief (email/SMS) │
│  • send alerts / brief       │ SQLite │  reads the same results  │
└──────────────────────────────┘        └──────────────────────────┘
        reuses src/ranch_ai (unchanged engine + tests)
```

- **One results table per pasture per day**: status (Good / Watch / Act), reason in plain words, inputs used, the source and date of each input, and confidence.
- **The worker owns failure.** If a source is down, it keeps yesterday's value and marks it stale. The app never calls an external API while the rancher waits.
- **Storage:** SQLite is enough at this scale if backups are on, with rasters (DEM, NDVI) cached as files. Move to Postgres/PostGIS only when several ranches share a server and need concurrent writes.

## The rancher-facing app (4 screens instead of 8 tabs)

1. **Today:** one row per pasture (🟢 Good / 🟡 Watch / 🔴 Act, with a one-line reason), rain in the last 7 and 30 days vs. normal, active NWS alerts, and fire danger.
2. **Pastures:** map plus a list. Tapping a pasture shows its card: grass trend in words with a small chart, rain, slope and terrain summary, last move, and days rested.
3. **Log:** Move herd · Rain gauge · Note/photo, each in 2 taps. It works offline in Phase 2.
4. **Settings:** ranch name, boundary (upload, or draw on the map), herds, and how to get alerts. Everything else goes under **Advanced**, admin only.

**Cut from the rancher view:** Data & Providers JSON, model metrics, calibration/shadow review, planner tables, Sensors (until it's live), scenario seed and modeling window. These stay available on an admin page.

## Phases

| Phase | Scope | Stack | Rough effort | Exit test |
|---|---|---|---|---|
| **0 (this week)** | Turn on DigitalOcean backups. Pin Streamlit. Merge PR #1 after the live terrain check. | — | hours | Backups visible in DO; app unchanged otherwise |
| **1: Robust** | Worker + results DB; Streamlit rebuilt as 4 `st.navigation` pages that only read results; demo ranch separated from real accounts; first-run boundary setup; UI smoke tests | Python only (your current skills) | ~2–3 weeks | Page load < 3 s with providers down; 0 external calls during page load; 3 ranchers complete setup alone |
| **2: Rancher-native** | Weekly brief (email first, SMS optional); phone-first view that works offline for Log and the last synced results | Small API + lightweight web app (PWA), or stay in Streamlit if Phase 1 testing shows phones are fine | ~4–8 weeks | Ranchers act on the brief without opening the app; logging works with no signal and syncs later |

## Risks and honest caveats

- **The status calls are only as good as the model.** Today the forage score is trained on a synthetic target (see `DATA_UPGRADE_PLAN.md`). A cleaner app will make those numbers *more* believable, so fix the target before ranchers rely on the Good/Watch/Act colors. Until then, base status only on observed inputs (rain vs. normal, NDVI vs. normal, RAP trend, drought, days rested) with simple, explainable rules.
- **A rewrite drops behavior that existing tests don't cover.** Phase 1 keeps `src/ranch_ai` and its tests unchanged and adds smoke tests for every page.
- **SMS costs money per message and needs consent handling.** Start with email.
- **Effort ranges are estimates** for one developer working with Claude. Validate them against Phase 1 actuals.

## Decisions needed

1. **Audience:** is this for your own land first, or a product for other ranchers? This changes how much account, onboarding and support work is needed.
2. **Phase 2 stack:** stay in Python/Streamlit (you can maintain it alone) or build a small PWA (better on phones and offline, but adds a JavaScript front end).
3. **Alerts:** email only, or also SMS?
