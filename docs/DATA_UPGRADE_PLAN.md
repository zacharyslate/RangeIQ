# RangeIQ Data Upgrade Plan

Reviewed 2026-10-12 against `main` @ `bfe0019`. Every external claim below links to a primary or official source.

## TL;DR

1. **More data won't improve the model until the training target is real.** `manual_forage_score` is a synthetic formula of the input features plus Gaussian noise (`src/ranch_ai/features/engineering.py`, lines ~167–180). The forage model is learning to invert that formula, so its MAE/R² say nothing about real pasture condition. None of the `public_*` features enter the formula, so to the model they are noise.
2. **Most current public inputs are coarser than the ranch.** The default parcel (Caja Caliente) is 4.77 ac (about 1.93 ha). NASA POWER meteorology is a 0.5° × 0.625° grid ([nasapower docs](https://docs.ropensci.org/nasapower/articles/nasapower.html)), roughly 55 × 60 km, and USDM is pulled at county level. Every pasture on the ranch gets identical values, so these columns cannot separate pastures from each other.
3. **The highest-value new data is fine-scale and static or slow-changing:** 1 m lidar terrain (shipped in this PR), RAP 10 m cover, PRISM 800 m daily climate, Ecological Site reference production, and Annual NLCD.

## 1. Critical issues in the current data/ML path

| # | Issue | Where | Why it matters | Fix |
|---|---|---|---|---|
| 1 | Synthetic target | `features/engineering.py` `forage_signal` | Model metrics are circular. A feature like `risk_score` is itself built from the same inputs as the target. | Replace the target with an observed quantity: RAP herbaceous production (annual or 16-day) as a weak label now, then the field feedback labels (`features/feedback_dataset.py`) and clip-plot weights as they accumulate. |
| 1b | Tiny training set | `pipeline.py` with the default ranch | The default run trains on **26 rows** (1 pasture × 26 weeks), so the 25 % test split is about 7 rows. Any reported metric is noise. | Pool across ranches and years, and train on multi-year history (RAP and NDVI go back years), not the 26-week display window. |
| 2 | Random row split on time series | `models/forage_model.py` `train_test_split(..., test_size=0.25)` | Adjacent weeks of the same pasture land on both sides of the split, so the reported error is optimistic (temporal leakage). | Use a blocked split by time (train on years ≤ N, test on N+1) or `GroupKFold` by pasture-season. |
| 3 | Scene-level cloud filter only | `vegetation/ndvi_client.py` `eo:cloud_cover <= 30` | A Sentinel-2 tile is about 110 × 110 km; 30 % tile cloud says nothing about whether this 2 ha parcel is clear. Clouds and shadows pull the NDVI means down. | Mask per pixel with the L2A Scene Classification (`scl`) asset: drop cloud, shadow, cirrus and snow classes, and require ≥ 80 % clear pixels inside the AOI before accepting a scene. |
| 4 | NDVI alone in sparse, high-soil-background range | same | Bright soil and sparse canopy in the Chihuahuan Desert compress NDVI's dynamic range. | Add a soil-adjusted index (SAVI/MSAVI2) and NDMI from the same scenes. It costs nothing extra, because the bands are already being read. |
| 5 | Earth Search collection naming is changing | `config.py` `ndvi_default_collection = "sentinel-2-l2a"` | Element 84 says v2 (beta) maps v1 `sentinel-2-c1-l2a` → v2 `sentinel-2-l2a` ([earth-search README](https://github.com/Element84/earth-search)). A silent switch would mix processing baselines in one time series. | Pin the STAC URL version and collection explicitly; prefer `sentinel-2-c1-l2a` on v1 for a consistently reprocessed archive. Keep reading `raster:bands` scale/offset per item (the current code does this correctly). |
| 6 | Unpinned Streamlit + deprecated API | `requirements.txt` `streamlit>=1.40`, `st.components.v1.html` for the Leaflet map | Streamlit 1.65 already logs "`st.components.v1.html` will be removed after 2026-06-01." That date has passed, so a fresh deploy could break the ranch map. | Pin `streamlit` to a tested range now; migrate the map to `st.iframe` or a custom component. |
| 7 | CSV + JSON-string geometry storage | `utils/io.py` `save_dataframe` | Loses types, is slow for history, and can't be queried spatially. | Store tables as GeoParquet and rasters as COGs, with STAC-style metadata for provenance. |

## 2. Recommended data additions (prioritized)

Priority is driven by (a) spatial resolution relative to a few-acre to few-thousand-acre ranch, (b) whether it is free and key-less, consistent with the project's open-data direction, and (c) direct relevance to stocking decisions.

### P0: terrain (done in this PR)

- **USGS 3DEP 1 m bare-earth DEM** from the [3DEP ImageServer](https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer) (F32, Web Mercator native, 8000 × 8000 export cap). The Caja Caliente parcel falls inside lidar project `TX_WestTexas_B7_2018` (EPT index: [hobuinc/usgs-lidar](https://github.com/hobuinc/usgs-lidar)). The project report lists it as **QL2**, collected 2019-03-06 to 2019-05-14 ([USGS project report](https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/metadata/TX_WestTexas_2018_D19/TX_WestTexas_2018_D19_Project_Report.pdf)). QL2 means ≥ 2 pts/m², 10 cm RMSEz (non-vegetated), and 1 m DEM posting ([USGS QLs](https://www.usgs.gov/3d-elevation-program/topographic-data-quality-levels-qls)).
- **Derived features:** slope, aspect, hillshade, and Holechek (1988) slope-class grazing reductions as tabulated in [NMSU Guide B-829](https://pubs.nmsu.edu/_b/B-829.pdf).
- **Caveat:** Holechek's classes predate 1 m lidar. RangeIQ classifies slope on a 10 m block-averaged DEM so that micro-relief does not inflate the slope numbers. Treat the result as a hypothesis to check against GPS-collar or observed use, not as truth.

### P1: high value, low effort

| Dataset | Resolution | Why for RangeIQ | Access |
|---|---|---|---|
| **RAP 10 m Cover** | 10 m, 2018–present ([RAP products](https://rangelands.app/products)) | About 193 pixels inside a 4.77 ac pasture versus about 21 at 30 m. Gives real within-ranch cover variation. The current client only uses the 30 m endpoints. | Free; same RAP platform |
| **PRISM daily** | 800 m, free since March 2025 ([PRISM orders](https://prism.oregonstate.edu/orders)) | Replaces NASA POWER's ~55 km cells for precipitation and temperature. Precipitation drives forage; spatial detail matters in mountainous Trans-Pecos terrain. | Free FTP / web services |
| **gridMET daily** | ~4 km, 1979–present ([GEE catalog](https://developers.google.com/earth-engine/datasets/catalog/IDAHO_EPSCOR_GRIDMET)) | Provides `erc`, `bi`, `fm100`, `fm1000`, `vpd` and `eto` directly. Gives the fire-risk service real NFDRS fuel indices instead of a heuristic, and supplies ET₀ for water balance. | Free (THREDDS / OPeNDAP) |
| **SSURGO by polygon, not centroid** | Survey scale | The audit notes soils are looked up at the pasture centroid. Intersecting polygons gives map-unit shares per pasture and links each pasture to its Ecological Site ID. | Free, existing SDA client |
| **Ecological Site Descriptions (EDIT)** | Per ecological site | Reference annual production (lb/ac) for favorable, normal and unfavorable years ([EDIT example](https://edit.sc.egov.usda.gov/catalogs/esd/048B/R048BY227CO/model)). This is the defensible baseline for carrying capacity that the current `estimated_carrying_capacity_au` lacks. | Free |

### P2: valuable, more work

| Dataset | Resolution | Why | Access / caveats |
|---|---|---|---|
| **3DEP lidar Height-Above-Ground** | 2 m COG ([PC collection](https://planetarycomputer.microsoft.com/api/stac/v1/collections/3dep-lidar-hag)) | Shrub and mesquite canopy height and brush-encroachment mapping, which links to RAP shrub trends. | One snapshot (2019 here). Planetary Computer STAC. |
| **Annual NLCD Collection 1.0** | 30 m, 1985–2023, 16 classes ([USGS release](https://www.usgs.gov/news/national-news-release/usgs-releases-new-products-map-four-decades-land-cover-change)) | Replaces the single-epoch NLCD scaffold with an annual land-cover change history. | Free |
| **OpenET** | Field scale; expanded to all 48 contiguous states (data available 2025-12-15) ([DRI](https://www.dri.edu/?p=1389993)) | Actual ET is a strong forage-growth signal in water-limited range. | Free API key needed (breaks the "no key" rule, so keep it optional). |
| **Distance to water** (NHD + user-mapped tanks) | Vector | Completes Holechek's other factor (distance-from-water reductions in [B-829](https://pubs.nmsu.edu/_b/B-829.pdf)), together with the new slope classes. | Free; needs user tank/trough input |
| **Grass-Cast** | 10 km grid ([Drought.gov](https://www.drought.gov/index%2Ephp/data-maps-tools/grassland-production-forecast-grass-cast)) | In-season production forecast. | Great Plains and Southwest regions only; Trans-Pecos coverage is unconfirmed, so verify before building. |

### Not recommended now

- **MODIS NDVI/EVI** (250 m): coarser than most pastures; Sentinel-2 plus RAP already cover this.
- **SMAP soil moisture** (km-scale, needs Earthdata login): too coarse and conflicts with the no-login direction. TexMesonet stations are a better local signal.

## 3. Suggested sequence

1. Fix issues 1–3 (target, split, cloud mask) before adding any feature. Without those fixes, the effect of new data cannot be measured.
2. Add terrain features (`slope_grazeable_fraction`, `relief_ft`, aspect) to `NUMERIC_FEATURES` and use slope-adjusted acres in carrying capacity.
3. Switch RAP to 10 m cover, add PRISM, and add gridMET fire indices.
4. Do the SSURGO polygon intersection, then pull ESD reference production per pasture.
5. Add lidar HAG brush mapping and Annual NLCD.

## 4. How to tell if an upgrade helped

Hold out the most recent full season. Compare MAE against an **observed** target (RAP production now, field labels later) for: (a) the current feature set, (b) plus terrain, (c) plus PRISM/gridMET, (d) plus RAP 10 m. Keep a feature only if it improves the held-out season error by more than the season-to-season noise. Report per-pasture errors, not just the ranch mean.
