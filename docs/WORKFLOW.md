# Processing workflow

From raw DJI images to orthophoto, DSM, DTM, point cloud and 3D model, using
OpenDroneMap in Docker on macOS (Apple Silicon). Every step is a command you can rerun.

```
raw JPGs ─► 1. inventory/QA ─► 2. preview (optional) ─► 3. full ODM run ─► 4. post-process, vegetation, 3DEP correction
                                                                          ─► 5. QA ─► 6. deliverables + cleanup ─► 7. view
```

All scripts write to a local working folder (`processing/<survey>/`, not in git). Only the final products
copied to `deliverables/<survey>/` in step 6 are meant to be kept and shared.

---

## 0. One-time setup

```bash
# Homebrew packages (all open source)
brew install colima docker gdal
brew install --cask qgis          # or the qgis.org installer

# Start the Docker VM. Give it most of the machine: ODM is RAM-hungry.
# (Tested on M1 Max, 10 cores / 64 GB: 8 CPUs / 48 GB to the VM.)
colima start --cpu 8 --memory 48 --disk 300 --arch aarch64 --vm-type vz --mount-type virtiofs

# Pull a pinned ODM version (native arm64 image)
docker pull opendronemap/odm:3.6.2
```

Notes:
- `colima stop` frees the RAM when you're done. `colima start` (no flags) restarts with the same settings.
  To change CPU/RAM: `colima stop && colima start --cpu N --memory M`.
- If `docker pull` fails with `docker-credential-desktop: executable file not found`, the
  `~/.docker/config.json` left behind by an old Docker Desktop install contains `"credsStore": "desktop"`.
  Remove that line, or run with a clean config: `DOCKER_CONFIG=$(mktemp -d) docker pull ...`.
- The project folder must be inside your home directory so Colima can mount it (the default mount is `~`).

## 1. Inventory and QA of the images

```bash
python3 scripts/inventory_images.py 2026-05-21_Map/Images_Mapping \
    -o 2026-05-21_Map/metadata/Images_Mapping_inventory.csv \
    --geojson 2026-05-21_Map/metadata/Images_Mapping_cameras.geojson
```

Check:
- **All images geotagged** and the **same camera** throughout.
- **Gimbal pitch ≈ −90°** (nadir). Any oblique or ground shots (like `Images_Nav/`) must be kept out of the mapping folder.
- **Relative altitude** is consistent (sets GSD).
- **Shot spacing / flight-line spacing → overlap.** See [DATA.md](DATA.md) for this dataset.
- Open the `cameras.geojson` in QGIS to check for coverage gaps.

## 2. Preview run (optional, minutes)

A fast orthophoto that skips dense reconstruction. Good for checking coverage and image quality right after a field day.

```bash
scripts/run_odm.sh 2026-05-21_Map/Images_Mapping 2026-05-21_Map_preview preview
```

To test the full pipeline on a small subset first (as done for this dataset with flight 3), put hard links to
~50 images in a temporary folder inside the project and run the `test` profile on it:

```bash
mkdir -p processing/_subset && ln -f 2026-05-21_Map/Images_Mapping/DJI_0{798..846}.JPG processing/_subset/
scripts/run_odm.sh processing/_subset test_subset test
```

Use hard links (`ln`), not symlinks. Symlinks pointing outside the mounted folder are invisible inside Docker.
Delete the subset and the test output when done. The hard links don't affect the raw photos.

## 3. Full ODM run

```bash
scripts/run_odm.sh 2026-05-21_Map/Images_Mapping 2026-05-21_Map full
```

What the script does:
- Mounts the image folder **read-only** at `/datasets/project/images`. Raw data are never modified.
- Writes all outputs to the working folder `processing/<project_name>/`.
- Reads ODM options from `config/odm_<profile>.args` (commented, one option per line).
- Saves a full timestamped log there, including the exact options.

### Options used (`config/odm_full.args`) and why

| Option | Value | Reason |
|---|---|---|
| `--feature-quality` | high | More/better SIFT features. Helps with repetitive grass texture and modest overlap. |
| `--pc-quality` | high | Denser point cloud, so more detailed DSM/DTM and better shrub definition. |
| `--pc-classify` | on | SMRF ground classification. The DTM is interpolated from ground points only. |
| `--rolling-shutter` | on | The Air 2S has a rolling shutter and flies continuously while shooting. ODM picks the FC3411 profile (32 ms readout) automatically. |
| `--dsm`, `--dtm` | on | Surface and bare-earth elevation models. |
| `--dem-resolution` | 5 cm | About 3× GSD. Finer than this only adds noise. |
| `--orthophoto-resolution` | 2 cm | Close to native GSD (1.75 cm). |
| `--auto-boundary` | on | Crops the poorly reconstructed fringe outside the flight area. |
| `--cog`, `--build-overviews` | on | Cloud-Optimized GeoTIFFs with overviews, so they load fast in QGIS and web maps. |
| `--gltf` | on | Also exports the textured 3D model as a single `.glb` file. |

To rerun only later stages (e.g., after changing DEM options), keep the project folder and add `--rerun-from`:

```bash
scripts/run_odm.sh 2026-05-21_Map/Images_Mapping 2026-05-21_Map full --rerun-from odm_dem
```

ODM stage order: `dataset → split → merge → opensfm → openmvs → odm_filterpoints → odm_meshing →
mvs_texturing → odm_georeferencing → odm_dem → odm_orthophoto → odm_report → odm_postprocess`.

### Main outputs

ODM produces the orthophoto, DSM, DTM, a classified point cloud, the textured 3D model (`.glb` with `--gltf`;
for older runs use `scripts/make_glb.sh`) and a QA report. It also writes large intermediate data, which
`scripts/cleanup_intermediate.sh` removes in step 6. Which outputs become deliverables is listed in step 6.

All rasters use the WGS84 / UTM zone CRS ODM picks automatically. For this site that is **UTM 13N, EPSG:32613**.

## 4. Post-processing (GDAL on the host)

```bash
scripts/postprocess.sh processing/2026-05-21_Map 0.5     # 0.5 m contour interval
```

Creates (in the working folder):

| File | Description | Rangeland use |
|---|---|---|
| `dtm_hillshade.tif`, `dsm_hillshade.tif` | Multidirectional hillshade | Visualize drainages, erosion, two-tracks, trails |
| `dtm_slope_deg_1m.tif` | Terrain slope (degrees) from the DTM averaged to 1 m | Erosion risk, grazing distribution |
| `dtm_slope_deg.tif` | Slope at full resolution (measures micro-relief) | Surface roughness |
| `dtm_color_relief.tif` | Colorized DTM | Quick-look elevation map |
| `chm.tif` | Vegetation height = DSM − DTM, clamped ≥ 0 | Shrub (e.g., sagebrush) height and cover, structure |
| `contours_<N>m.gpkg` | DTM contours (from the 1 m DTM) | Maps, water flow, layout |
| `summary.txt` | CRS, resolution, extents, elevation stats | Record keeping |

## 4b. Fine-scale vegetation (short grass / low shrubs)

```bash
scripts/vegetation_chm.sh processing/2026-05-21_Map 0.10
```

Reclassifies the point cloud with a fine SMRF (threshold 0.05 m, window 2 m), computes height above ground
per point, and writes a vegetation height raster (10 cm), a vegetation mask, a 1 m vegetation-cover raster, a fine
DTM and a reclassified point cloud with a `HeightAboveGround` attribute. ODM's outputs are left untouched. Method, parameter comparison and known
artifacts are in [VEGETATION.md](VEGETATION.md).

## 4c. Vertical check and correction against USGS 3DEP (US sites)

Without GCPs/RTK, ODM's heights carry a constant offset and a smooth bowl ("doming") distortion.
For 2026-05-21_Map: −40.8 m offset and a 13.6 m bowl. `correct_dem_3dep.py` downloads the USGS 3DEP lidar DEM,
fits a 2nd-order surface to (drone − 3DEP) and writes corrected DEMs in NAVD88 (residual 0.12 m RMSE here).
Then rerun `postprocess.sh` on the corrected DEMs:

```bash
QPY=/Applications/QGIS-final-4_2_3.app/Contents/MacOS/python    # Python with GDAL + numpy
$QPY scripts/correct_dem_3dep.py processing/2026-05-21_Map
P=processing/2026-05-21_Map
DSM=$P/corrected/dsm_navd88.tif DTM=$P/corrected/dtm_navd88.tif OUT=$P/derived_navd88 scripts/postprocess.sh $P 0.25
```

**Always run this check** when no ground control is available, and use the corrected DEMs and the terrain
products made from them for elevation work. They are the ones copied to the deliverables in step 6.

## 4d. Report and QGIS project

`make_report_figures.py` and `make_qgis_project.py` build `docs/REPORT.md`'s figures and a pre-styled QGIS
project (`qgis/<survey>.qgz`). See [REPORT.md §9](REPORT.md#9-reproducing-this-report).

## 5. QA checklist

1. **ODM quality report (PDF)**:
   - Reconstructed images: ideally > 95 % of input images.
   - Overlap map: at least 5 images per point over the area of interest.
   - GPS errors: a few metres is normal without RTK/GCPs.
   - Number of reconstructions: should be 1. More than 1 means a gap split the model.
2. **Orthophoto in QGIS**: look for seamlines, smearing, holes, and ghosted moving objects (livestock, vehicles).
3. **DTM**: hillshade should look smooth. Bumps where shrubs are mean classification left vegetation in. Try tuning `--smrf-threshold` / `--smrf-window`.
4. **CHM**: check heights against a few field-measured shrubs if available.
5. Write run notes (date, ODM version, profile, runtime, issues) in [PROCESSING_LOG.md](PROCESSING_LOG.md).

## 6. Deliverables and cleanup

```bash
scripts/make_deliverables.sh 2026-05-21_Map                 # copy final products, verify they're identical
scripts/cleanup_intermediate.sh 2026-05-21_Map              # dry run: lists what would be deleted
scripts/cleanup_intermediate.sh 2026-05-21_Map --yes        # delete intermediate ODM data (75 GB → 13 GB here)
```

`make_deliverables.sh` copies these into `deliverables/<survey>/` (on macOS as space-free clones). Then write a
`README.txt` for the folder; the 2026-05-21_Map one is a template.

| Deliverable | Content |
|---|---|
| `<date>_orthophoto_2cm.tif` | Orthophoto |
| `<date>_DTM_5cm_NAVD88.tif`, `<date>_DSM_5cm_NAVD88.tif` | DTM and DSM corrected to USGS 3DEP |
| `<date>_contours_0.25m_NAVD88.gpkg`, `<date>_slope_1m_degrees.tif` | Contours and terrain slope (corrected) |
| `<date>_vegetation_cover_1m.tif` | Vegetation cover ≥ 10 cm |
| `<date>_point_cloud_classified_HAG.laz` | Point cloud with ground class + height above ground |
| `<date>_3D_model_textured.glb` | Textured 3D model |
| `<date>_ODM_quality_report.pdf` | ODM QA report |

`cleanup_intermediate.sh` removes ODM's intermediate data and the parameter-test folders. Final products, the
layers used by the QGIS project, reference data and logs are kept. Afterwards ODM can't `--rerun-from` a later
stage: reprocessing means a full run from the raw photos.

## 7. Viewing

- **QGIS**: drag in the deliverables (`.tif`, `.gpkg`, `.laz`). QGIS 3.18+ shows point clouds natively, with a 3D
  view. For every layer pre-styled, open `qgis/<survey>.qgz` (needs the local working folder).
- **3D model**: open the `.glb` in any glTF viewer (e.g. gltf-viewer.donmccurdy.com, 3dviewer.net) or Blender.
- **WebODM** (optional GUI): import the same images, or upload the deliverables.
- Interpretation guide: [REPORT.md](REPORT.md).

## Tuning notes for rangeland

- **Low-contrast grass**: if images fail to match, try `--feature-type sift` (default) with `--min-num-features 15000`, or `--matcher-neighbors 12`.
- **Short-grass sites (DTM ≈ DSM)**: SMRF treats anything under ~0.5 m as ground. On short-grass steppe
  (like 2026-05-21_Map) almost every point becomes ground, so DTM ≈ DSM and the CHM is near zero. That is
  expected behaviour. Use `scripts/vegetation_chm.sh` (step 4b) for fine-scale vegetation instead.
- **Shrubs in the DTM**: lower `--smrf-threshold` (default 0.5 m) to 0.3 m, or raise `--smrf-window` (default 18 m) for larger shrub patches.
- **Edge artifacts**: `--auto-boundary` already crops. Add `--boundary my_area.geojson` for an exact study plot.
- **Memory errors / OOM**: lower `--pc-quality` to `medium`, raise Colima memory, or use `--split 200 --split-overlap 50` (split-merge).
- **Repeat surveys**: add GCPs (`--gcp gcp_list.txt`) or align to the previous survey (`--align previous_model.laz`) so change detection works.
