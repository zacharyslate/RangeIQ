# RangeIQ phone app: ranch-hand edition

What changed, why, and what the numbers can and can't tell you.

## The simplification

The old phone app had five tabs (Today, Pastures, 3D, Log, More), a status explainer on the main screen, and data-source detail mixed into every page. A ranch hand opening it in a pickup needs to do one of four things, so the app now opens on those four things.

| Before | Now |
| --- | --- |
| Today, Pastures, 3D, Log, More | **Home, Map, Log, More** |
| Logging hidden on the Log tab | Four big buttons on Home: **Take photo, Rain gauge, Moved cattle, Report problem** |
| One card per pasture, even when all six said the same thing | **Needs attention** groups identical reasons ("All pastures: Watch, extreme drought (D3)") and puts crew reports first |
| 3D was its own tab | Map has a **Map / 3D** switch; 3D has a **Photo / Topo** switch |
| "Report" meant typing a note | Tap chips (Water low, Fence down, Gate open, Dead animal…), with an optional note |
| One login per ranch | **Crew codes**: the owner makes a code (like `K7M-4QX`), the hand joins with it and works on the owner's ranch, credited by name, but can't change settings |
| Data sources and status rules on the main screens | Moved into collapsible sections under More |

Everything a hand records (photos, rain, moves, problems) is saved on the phone first and sent when there's signal. A "waiting to send" pill shows what hasn't gone yet.

## Camera

1. **Take photo** opens the phone camera. While the photo is being taken the app reads GPS (`watchPosition`, high accuracy, keeps the best fix for up to ~6 s) and the compass (`deviceorientationabsolute` on Android, `webkitCompassHeading` on iPhone after the one-time permission prompt).
2. On the phone, with no signal needed, it measures:
   - **Green %**: the Canopeo color rule (R/G < 0.95, B/G < 0.95, 2G−R−B > 20) on a 200-px-wide copy, with sky pixels left out.
   - **Brown or bare %**: tan/brown pixels.
   - **Change vs. the last photo from the same spot** (within 35 m, facing within ±45°). A drop of 15 points or more flags the photo.
3. The hand taps what the photo shows (optional), the pasture is filled in from GPS, and the photo is saved (1600 px JPEG plus a 360 px thumbnail) and queued.
4. On the server, photos are private to the ranch and are served through signed links that expire.
5. Photos appear as pins on the 2D map (with a wedge showing the direction the camera faced) and on the 3D view, and in the pasture page and the Log. Photos taken from the same spot share one pin. Opening one shows **"This spot over time"**.

### What a hand can report

Photos and the **Report** button share one list of quick-tap tags, in five groups that open one at a time:

| Group | Tags (level) |
| --- | --- |
| 💧 Water | Water low, Trough or tank problem, Windmill or pump down (serious) · Pipe or float leak (watch) · Water OK (good) |
| 🚧 Fences, gates & roads | Fence down (serious) · Fence damaged, Gate open, Gate damaged, Cattle guard problem, Washed-out road (watch) |
| 🐄 Livestock | Cattle out, Sick or hurt animal, Dead animal (serious) · Stray animal (watch) · New calf (sighting) |
| 🦌 Wildlife | Feral hogs, Hog rooting damage, Coyote or predator (watch) · Rattlesnake (heads-up) · Deer, Other wildlife (sighting) |
| 🌾 Grass & land | Fire or smoke (serious) · Short or overgrazed grass, Weeds or brush, Poisonous plants, Erosion or washout (watch) · Good grass (good) |

- **Serious** and **watch** tags feed pasture status for 14 days and show on Home for 3 days.
- **Heads-up** (rattlesnake) shows on Home for 3 days so people know, but doesn't change pasture status.
- **Sightings** (deer, new calf) are kept in the Log (filter: Wildlife) and on the map, but don't raise an alarm.
- Reports save the phone's GPS location when it's available, so every report, not only photos, shows as a pin with its own icon (🐗, 🐍, 🚧, 💧…) on the 2D and 3D maps.

The tag list lives in two places, `TAG_LEVELS` in `src/ranch_ai/rancher/status.py` and `TAG_GROUPS` in `web/app/app.js`, and a test fails if they differ.

A problem tag (Water low, Fence down, Dead animal…) on a photo or a report feeds the pasture status for 14 days. A serious one (concern level) makes the pasture **Act** on its own, because it is a direct observation. Satellite and weather data still need two things off before they say Act.

## Honest limits

- **Green % is a color count, not a forage measurement.** Canopeo was validated for fractional green canopy cover from overhead photos, with good agreement against other methods (Patrignani & Ochsner 2015). Ranch photos are oblique, so the share of the frame that is near ground versus far ground changes the number. Shadows, low sun, and green-tinged water or algae also change it. Use it to compare **the same spot, same direction, similar time of day** (repeat photo points; Hall 2002). Don't use it to compare two different pastures.
- **Brown or bare lumps dry grass and bare soil together.** In a normal RGB photo they look alike.
- **Sky removal is a heuristic** (blue-dominant or very bright pixels in the top half). Grey overcast skies may count as ground.
- **The compass on a phone is often 10–20° off**, worse near trucks, fences and steel tanks. Direction is good enough to tell "facing the tank" from "facing the gate", not for surveying.
- **GPS is usually ±5–10 m in the open.** The app shows the accuracy with each photo. Photos taken before a fix arrives are saved without a location, and the hand picks the pasture.
- **Water level is not measured from the photo.** The hand tags "Water low" or "Water OK". Reading a tank level automatically would need a fixed camera or a float sensor.
- **Storage**: photos stay on the server's disk (about 0.3 MB each). There is no automatic cleanup yet.

## 3D view

- **Glowing walls**: each pasture boundary is a wall that fades upward. Green means Good, gold means Watch, red (pulsing) means Act. There is also a bright line on the ground so the boundary reads from straight above.
- **Photo** look: the USDA NAIP aerial photo, under a low evening sun.
- **Topo** look: earth-tone elevation colors with hillshade from the north-west and contour lines. The interval is picked to give about 10–14 lines (for example "every 20 ft"), with every fifth line darker.
- Photo pins are placed by converting the phone's GPS to the terrain's UTM grid in the browser (Snyder 1987 formulas). This matches rasterio to under a millimetre.

## References

- Patrignani, A., & Ochsner, T. E. (2015). Canopeo: A powerful new tool for measuring fractional green canopy cover. *Agronomy Journal*, 107(6), 2312–2320. https://doi.org/10.2134/agronj15.0150
- Hall, F. C. (2002). *Photo point monitoring handbook* (Gen. Tech. Rep. PNW-GTR-526). USDA Forest Service, Pacific Northwest Research Station. https://doi.org/10.2737/PNW-GTR-526
- Snyder, J. P. (1987). *Map projections: A working manual* (USGS Professional Paper 1395). https://doi.org/10.3133/pp1395

## To do (jobs around the ranch)

- **Who can add and check off:** anyone on the ranch (owner, partner or crew) can add a job, and anyone can check it off. The app records who checked it off and when.
- **Job details:** a title (or one-tap ideas like "Check waters" or "Fix fence"), when it's due, a repeat (every day, 2 or 3 days, week, 2 weeks, month), the pasture, the person, and notes.
- **Repeating jobs** move their due date on from the day they were done ("Check waters every 2 days"), and the list shows who did them last.
- **Home** shows what's overdue or due today with a big check box. The **To do** tab groups jobs into Overdue, Today, Coming up and Any time. Jobs done in the last 2 weeks stay visible, and can be un-checked by the person who did them or by the owner.
- **Make it a job:** any photo or report has a **Make it a job** button. It copies the problem, the pasture and the location into a new job.
- **Works offline:** jobs work with no signal. Changes are saved on the phone and sent later. Each change has its own id, so sending it twice does nothing.

## One login, several ranches

- A person can be on several ranches: the owner of their own, and a **partner** or **crew** on others.
- The owner makes a **crew code** (ranch hands) or a **partner code** (a co-owner or manager with the same rights; it works once and lasts 2 days).
- Someone who already has a login joins with their own email and password. The ranch is added to their account.
- With more than one ranch, tap the ranch name at the top (or More → Your ranches) to switch. The app reopens on the last ranch used.
- Switching waits until everything recorded for the current ranch has been sent, so nothing lands on the wrong ranch.

## Staying signed in

- A phone sign-in lasts a year and renews itself whenever the app is used, so a hand who opens it regularly never has to sign in again.
- The app opens straight to Home.
- On iPhone, the Home Screen app keeps its own sign-in, separate from Safari. Add it to the Home Screen first, then sign in there once.
- New owner accounts are closed (`RANGEIQ_OPEN_SIGNUP=1` reopens them). Crew and partner codes still work.

## Satellite greenness

- The worker reads each Sentinel-2 scene **once for the whole ranch** (red, near-infrared, and the scene classification layer to drop cloud, shadow, snow and water). It keeps a pasture's value only when at least half of that pasture is clear.
- Results are stored, so each hourly run only reads new scenes, within a 5-minute budget, newest first.
- On Clear Creek Ranch (29 pastures, 4 years, 98 scenes) the first full load took 220 s, against hours for the old per-pasture pull.
- Greenness compares the last 30 days with the same ±20-day window in earlier years (needs at least 2 earlier years).

## The map as a console

- **Opens in 3D every time.** If the 3D terrain isn't ready, or the phone can't draw 3D, it falls back to the flat map.
- **🗂 Layers** turns things on and off. The choices are kept on the phone.
  - Pastures, and **Warning colors**: off gives neutral boundary lines.
  - Water, Hunting, Ranch places and Sensors (the ranch's own places).
  - **USGS water map**: mapped ponds, stock tanks, springs, wells and dams.
  - Wildlife & sightings, Problems, other Photos, and Jobs that have a location.
- **＋ Place** adds a fixed place to the map.
  - Water: water tank, trough, pond or dirt tank, windmill or well.
  - Hunting: deer blind, feeder, game camera, stand.
  - Ranch: gate, cattle guard, pens, building, mineral or salt.
  - Sensors: rain gauge, water level, soil moisture, weather station.
  - Each place has a name, an optional photo and notes, and its location comes from the phone's GPS or a tap on the 2D or 3D map. Taps on the 3D ground are turned back into GPS coordinates; the UTM math round-trips to under a millimetre.
  - Places can be edited and deleted by the owner or whoever added them. They work offline.
- **Sensors** carry an optional device ID (from the sensor's label), so readings can be attached to the pin once sensors are connected.
- **USGS water map:** from the National Hydrography Dataset (Waterbody and Point layers of `hydro.nationalmap.gov/.../nhd/MapServer`), refreshed every 30 days. NHD was mapped from older imagery, so it misses some dirt tanks and shows some that are dry. Each one has **Save as our place**.

## Warnings

- **Ignore drought & low rain in pasture status** (in More, or in the map's Layers panel). Drought and rain are the same for every pasture and often "normal" out here.
- With it on, status comes from each pasture's own evidence: greenness, long-term trend, grazing days and crew reports.
- Home then shows one line saying what was left out. Severe-weather alerts and crew reports always show.

## Sun, moon and forecast

- Home shows the 7-day forecast with weather icons.
- It also shows sunrise and sunset, first and last light, the moon phase (% lit, next full and new moon), and moonrise and moonset, for the middle of the ranch in ranch time.
- The sun and moon are worked out on the phone (`web/app/sky.js`, low-precision Meeus formulas), so they work with no signal.
- Checked against PyEphem: sun times within 2 minutes; moonrise and moonset within about 4 minutes; % lit within 0.6 points; next full and new moon within about 5 hours. Only the date is shown for those.

## 3D detail

- **Terrain:** 512 × 512 vertices (was 256) from the USGS 3DEP lidar elevation.
- **Aerial photo:** 3072 px USDA NAIP (was 1024), about 2.4 m per pixel on a 7 km ranch. The NAIP service allows up to 4000 px per request.
- Both are rebuilt only when the format, the boundary or the month changes.
- **Possible next step:** zoom-in detail tiles that load 1 m lidar and 0.6 m NAIP around where you're looking.
- **Google Photorealistic 3D Tiles were considered and not used:**
  - They are not available to Google Maps Platform projects billed to an EEA address (HTTP 403 since 8 July 2025).
  - Their terms prohibit offline caching.
  - They require Google attribution on screen.
