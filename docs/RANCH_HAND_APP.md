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
