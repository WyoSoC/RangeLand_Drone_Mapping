# Processing log

One entry per ODM run. Copy the template at the bottom for new runs.

Machine: Apple M1 Max, 10 cores, 64 GB RAM, macOS. Colima VM: 8 CPU / 48 GB / vz + virtiofs.
ODM: `opendronemap/odm:3.6.2` (arm64).

---

## 2026-11-05: `test_flight3` (pipeline test)

- **Input:** flight 3 only, DJI_0798–DJI_0846 (49 images), hard-linked into `processing/_subsets/flight3`
- **Profile:** `config/odm_test.args` (medium feature/pc quality, DSM+DTM 10 cm, ortho 5 cm)
- **Purpose:** check that Docker/Colima mounts, the DJI metadata, rolling-shutter correction and all output stages work before the multi-hour full run.
- **Notes:**
  - Rolling shutter profile found automatically: `DJI FC3411`, 32 ms readout.
  - Warning: *Multiple reconstructions detected (2)*. Flight 3 alone doesn't have enough side overlap to link every strip.
  - The pull with the global Docker config failed (`docker-credential-desktop` left over from Docker Desktop). Fixed by running with a clean `DOCKER_CONFIG`. See WORKFLOW §0.
- **Runtime:** ~13 min (18:57 → 19:10 UTC)
- **Reconstructed images:** 48/49, 1 component after merge (ODM merged the 2 partial reconstructions using GPS)
- **GPS average error (SfM vs EXIF):** 6.0 m. Normal for a consumer drone without RTK or GCPs.
- **Outputs:** ortho 5 cm (13955 × 13128 px), DSM/DTM 10 cm, EPSG:32613 (UTM 13N)
- **Elevations:** DSM 2131–2222 m, mean 2159.5 m. CHM 0–11 m, mean 0.11 m.
- **Post-processing:** all products created. The first version of `postprocess.sh` used `gdal raster calc`,
  which fails on Homebrew GDAL ("Dialect 'muparser' is not supported"). Replaced it with a VRT `diff` pixel
  function plus `gdal raster reclassify`.
- **QA:** the flight-3 footprint is fragmented: an isolated single flight line plus a block with a gap between them.
  The DTM shows interpolation artifacts across the gap. Flight 3 is a partial fill-in, so this is expected,
  and the test still confirms every stage works.
- **Result:** ✅ pipeline validated → proceed to the full run.

---

## 2026-11-05: `2026-05-21_Map` (full run)

- **Input:** `2026-05-21_Map/Images_Mapping`, 494 images (Images_Nav excluded)
- **Profile:** `config/odm_full.args`
- **Runtime:** **3 h 07 m** (12:13 → 15:21 local). Post-processing (`postprocess.sh`): 8.5 min.
  - SfM 29 min (features 7.6 min, matching 3.3 min, reconstruction plus rolling-shutter re-solve 18 min). Mostly single-core, ~4.5 GB RAM.
  - OpenMVS dense: ~55 min on all 8 cores. **Peak RAM about 34 GB** during depth-map fusion, out of 48 GB in the VM.
  - Meshing, texturing, DEMs, orthophoto, report: the rest.
- **Reconstruction:** **494/494 images**, **1 component**, 931,931 sparse points, mean track length 3.1 images
  (short tracks, consistent with the modest overlap). Reprojection error 0.90 px.
- **GPS vs SfM camera positions:** RMS x 2.9 m, y 2.3 m, z 2.8 m (CE90 4.4 m, LE90 4.3 m). Normal for non-RTK.
- **Outputs** (EPSG:32613, WGS84 / UTM 13N; 64 GB project folder in total):

  | Product | Size / resolution | File size |
  |---|---|---|
  | Orthophoto | 60388 × 47123 px @ 2 cm (mean GSD 1.82 cm) | 3.0 GB COG |
  | DSM / DTM | 24154 × 18848 px @ 5 cm | 365 / 363 MB COG |
  | Point cloud | 126.8 M points, classified | 450 MB `.laz`, 4.6 GB `.las` |
  | Textured mesh | `.obj` + 64 texture atlases | ~2.8 GB |
  | Mapped area | 97.6 ha (≈ 1.2 × 0.94 km bounding box) | |

- **Elevations:** 2141.8 – 2161.2 m (≈ 19 m relief across the site), mean 2146.5 m (GPS ellipsoidal heights, not survey-grade).
- **QA (visual):** orthophoto is seamless with no visible holes. Tracks, two-tracks, drainages and a circular
  disturbance/outcrop feature are clear in both the ortho and the hillshades. Clumps of individual plants
  (~10–20 cm mounds) show in the 5 cm DSM. Faint diagonal striping along flight-line direction in the hillshade
  comes from the low side overlap (50 %).
- **Finding: DTM ≈ DSM, CHM ≈ 0.** PDAL shows 99.99 % of points classified as ground (class 2). This is correct
  for this site: it is short-grass steppe, and nothing stands taller than ODM's default ground-filter threshold
  (`--smrf-threshold 0.5 m`). The CHM (mean 3 mm, max 1.3 m) is not meaningful here. Use the DSM for microtopography and
  plant-clump relief. To try separating low vegetation: rerun with `--rerun-from odm_dem --smrf-threshold 0.15 --smrf-window 5`
  (experimental; it approaches the ~5 cm vertical noise of photogrammetry).
- **Result:** ✅ all products created and checked.

---

## 2026-11-05: `2026-05-21_Map` vegetation (fine-scale ground filter)

- **Goal:** recover low vegetation that ODM's default ground filter merges into the DTM.
- **Script:** `scripts/vegetation_chm.sh processing/2026-05-21_Map 0.10` (PDAL inside the ODM container)
- **Parameter test:** 5 ground filters on a 200 × 200 m tile (SMRF default / t0.15 w5 / t0.10 w3 / **t0.05 w2** / CSF).
  The most aggressive SMRF (threshold 0.05 m, window 2 m, slope 0.2, scalar 1.0) was picked. Details in [VEGETATION.md](VEGETATION.md).
- **Runtime:** 6 min for the full cloud (PDAL ~4 min, ~15 GB RAM).
- **Result:** ground share 100 % → ~77 % on the test tile. Vegetation cover ≥ 0.10 m = **3.9 %** of the site.
  CHM max 2.43 m. Real vegetation patterns are visible (ring around the circular feature, darker patches).
- **Issue: ghost layers.** Straight bands and an L-shape come from doubled surfaces ~10–20 cm apart where
  overlapping images disagree (sampled: 370 pts/m² in two layers vs ~130 pts/m² normally). Smaller windows,
  mean-HAG, point density and higher thresholds did not separate them from real vegetation. Documented as a
  known artifact. Root cause: 50 % side overlap.
- **Bugs fixed on the way:**
  - The 1 m cover raster was resampled from cubic COG overviews (max 1.6) → `gdalwarp -ovr NONE` plus
    `OVERVIEW_RESAMPLING=NEAREST` for the mask.
  - Byte mask nodata handling → VRT without nodata, then reclassify to 255.

---

## 2026-11-05: `2026-05-21_Map` vertical check, correction, report

- **Vertical check vs USGS 3DEP** (`correct_dem_3dep.py`, 2 m grid, 156k cells): raw ODM DTM = 3DEP − 40.8 m (std 2.9 m),
  with a **bowl ("doming") distortion of 13.6 m**: centre too low, edges too high. A 2nd-order polynomial fit removes it.
  Residual **0.12 m RMSE**, p05/p95 −0.20/+0.18 m. Spot checks at 11 USGS EPQS points: within 0.00–0.34 m.
- **Corrected DEMs** written to `corrected/*_navd88.tif`. Terrain products regenerated into `derived_navd88/`
  (0.25 m contours).
- **postprocess.sh changes:** contours are now generated from a 1 m-averaged DTM (the 5 cm DTM gave 56k noisy rings,
  132 MB → 5.7k lines, 3 MB). Added `dtm_slope_deg_1m.tif` (terrain slope, median 1.5°). The 5 cm slope
  (median ≈ 5°) mostly measures grass-hummock roughness.
- **Report:** `docs/REPORT.md` with 13 figures (`make_report_figures.py`), point-cloud slices (`export_section.sh`)
  and a pre-styled QGIS project `qgis/2026-05-21_Map.qgz` (`make_qgis_project.py`).
- Added `--gltf` to `config/odm_full.args` for future runs (no `.glb` was produced this time).

---

## 2026-11-05: `2026-05-21_Map` glTF model

- Created `odm_texturing/odm_textured_model_geo.glb` from the existing textured OBJ with `scripts/make_glb.sh`.
  It calls ODM's own `opendm.gltf.obj2glb` with the UTM offset from `coords.txt`, the same as `--gltf`, and
  needs no stage rerun.
- 1.5 min. 269 MB (from ~2.8 GB OBJ + PNG textures): Draco-compressed mesh, 197,052 vertices, 64 JPEG textures,
  `CESIUM_RTC` centre (443997, 4569496). Validated: glTF 2.0 header, extensions `CESIUM_RTC`,
  `KHR_draco_mesh_compression`, `KHR_materials_unlit`. Heights are raw ODM values (2135.9–2159.1 m).

---

## Template

```
## YYYY-MM-DD: `<project_name>`

- **Input:** <folder>, <N> images
- **Profile:** config/odm_<profile>.args  (+ extra args: ...)
- **ODM version:** 3.6.2
- **Runtime:** <hh:mm>
- **Reconstructed images:** <n>/<N>, reconstructions: <k>
- **Outputs:** ortho <res> cm, DSM/DTM <res> cm, point cloud <n> pts
- **QA notes:** <report.pdf observations, artifacts, GPS residuals>
- **Issues / fixes:**
```
