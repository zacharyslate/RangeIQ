# RangeIQ Usability & Complexity Review

Reviewed 2026-10-12 by running the app headless and logging in as a new test account. Every tab was screenshotted, and widgets were counted per tab with Streamlit's `AppTest`.

**Caveat:** the review environment blocks outbound calls to the data providers, so every provider fell back to mock data and the map tiles were blank. The layout and complexity findings don't depend on that.

## Verdict

RangeIQ is **too complex for its primary user today**. The visual design is polished and the fallbacks never crash, but the app shows a rancher what a developer would want to see: model internals, raw JSON, provider plumbing, and simulation knobs. It also repeats the same pasture status in several places. With one 4.8-acre pasture, the app presents 8 tabs, 82 inputs and 4 copies of the same status table.

## Evidence

| Tab | Inputs | Raw JSON blocks | Approx. page height | Notes |
|---|---|---|---|---|
| Dashboard | 2 | 0 | 4,600 px | 9 sections; "Priority Attention Items" and "Ranch-Wide Attention Queue" show the same row |
| Management Units | 16 | 0 | 2,800 px | Metadata editor plus field labels plus another copy of the status table |
| Vegetation & Land Health | 1 | 0 | 2,700 px | Good focus |
| 3D Terrain (new) | 4 | 1 (collapsed) | 2,200 px | |
| Livestock & Management | 20 | 0 | 2,800 px | Two separate editors (groups, activities) plus 2 more status tables |
| Data & Providers | 0 | **5** | **9,000 px** | Server file paths, raw exception text, ML dataset column lists |
| Settings | **37** | **10** | 2,300 px | 5 sub-tabs; save button buried in "Operations & Save" |
| Sensors | 0 | 0 | small | "Under development" placeholder only |
| **App-wide** | **82** | **16** | | |

## Fixed in this PR (clear bugs)

1. **The ranch header rendered at the bottom of every tab.** It was created after `st.tabs(...)`, and Streamlit renders elements in creation order. It is now placed in a slot reserved above the tabs.
2. **Button labels were unreadable:** dark text on the dark-green gradient. Streamlit wraps labels in `<p>`, which overrode `color: white`. The labels now render white.
3. **The KPI contradicted the unit card.** "Attention Queue: 0" counted only `High`, while the selected unit was `Elevated`. The KPI is renamed "Needs Attention" and counts Elevated and High.
4. **Misleading green arrows on KPI deltas.** A condition score of 43/100 showed a green ↑. Deltas are now neutral (`delta_color="off"`).
5. **Broken sentence:** "Management Unit condition is needs attention with…" now reads "Management Unit condition: needs attention. Vegetation normal; drought status D1."

## Recommendations (need your decision)

### P0: trust and honesty

- **Label synthetic numbers.** Condition score, water risk, attention score and the recommendation all come from the synthetic pasture-week generator. The forage model is trained on **26 rows** (1 pasture × 26 weeks; see Data & Providers → Hybrid Training Dataset). A rancher will read "Condition 43.2" as a measurement. Until a real target exists (see `DATA_UPGRADE_PLAN.md`), either badge every synthetic-derived value as **Demo** or hide those scores and lead with the observed data: weather, alerts, drought, NDVI/RAP and terrain.
- **New accounts inherit the Caja Caliente boundary.** `default_pasture_path` points at `caja_caliente_ranch.geojson`, so every new sign-up sees your parcel and address with the message "drawn from your provided Alpine property corners." Replace this with a first-run step: draw or upload a boundary, or start from a clearly labeled sample ranch.
- **Don't show raw exceptions to users.** The provider status table prints proxy errors and full request URLs. Show "Weather: live / demo" in the main view and keep the details for admins.

### P1: cut complexity

- **Go from 8 tabs to 5, organized around rancher questions:**
  1. **Today:** weather, alerts, fire risk, and the 1–3 actions that matter
  2. **Pastures:** map plus one card per pasture (condition, land-health trend, terrain summary)
  3. **Herd & Moves:** one "log a move" form that combines the group and activity editors
  4. **Land:** vegetation history and 3D terrain
  5. **Settings:** basic setup, with an **Advanced** expander
  
  Move Data & Providers and the JSON summaries in Settings into an **Admin / Diagnostics** page behind a role or toggle. Hide **Sensors** until it works.
- **Show the status table once.** Today it appears 4 times (2 on Dashboard, 1 in Units, 1 in Livestock).
- **Remove simulation knobs from user settings.** "Scenario seed", "Weekly modeling window" and per-source "Refresh (h)" are developer controls.
- **Make saving obvious.** Auto-save, or a sticky "Save" button; right now unsaved changes are easy to lose.
- **Use plain language.** "Management Unit" should become "Pasture" for cattle ranches by default (the terminology setting already exists). Suggested renames:
  - "AUD/acre (30d)" → "Animal-days per acre, last 30 days"
  - "Utilization heuristic" → "Grazing use, last 30 days"
  - Drop "Load heuristic"
  - "Shadow review", "Calibration", "Hybrid training dataset" → admin only
  - Show every score as "x / 100" with what counts as good.

### P2: polish and performance

- Format the forecast as whole °F; today's high and low were identical (65.40 / 65.40).
- First load took about 45 s to render here, although provider timeouts inflated that. Streamlit runs every tab's code on every interaction. Use `st.navigation` pages or `st.fragment` so only the visible section recomputes.
- Pin `streamlit` and migrate the Leaflet map off `st.components.v1.html`. Streamlit 1.65 warns that it "will be removed after 2026-06-01," and that date has passed.

## What already works well

- Field Mode for phones is a smart call for people working outdoors.
- The visual theme is consistent and calm, and dark mode is thoughtful.
- Fallbacks keep the app alive when providers fail.
- Explanations sit next to the heuristics, which fits the "transparent, not black-box" goal in `PROJECT_BRIEF.md`. Keep that tone and trim the volume.
