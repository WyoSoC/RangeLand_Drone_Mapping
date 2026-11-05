# Processing workflow

From raw DJI images to orthophoto, DSM, DTM, point cloud and 3D model, using
OpenDroneMap in Docker on macOS (Apple Silicon). Every step is a command you can rerun.

```
raw JPGs ──► 1. inventory/QA ──► 2. preview run (optional) ──► 3. full ODM run ──► 4. post-process (GDAL) ──► 5. QA + view in QGIS
              scripts/             config/odm_preview.args      config/odm_full.args    scripts/postprocess.sh
              inventory_images.py
```

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

To test the full pipeline on a small subset first (as done for this dataset with flight 3):

```bash
mkdir -p processing/_subsets/flight3
for f in 2026-05-21_Map/Images_Mapping/DJI_0{798..846}.JPG; do ln -f "$f" processing/_subsets/flight3/; done
scripts/run_odm.sh processing/_subsets/flight3 test_flight3 test
```

Use hard links (`ln`), not symlinks. Symlinks pointing outside the mounted folder are invisible inside Docker.

## 3. Full ODM run

```bash
scripts/run_odm.sh 2026-05-21_Map/Images_Mapping 2026-05-21_Map full
```

What the script does:
- Mounts the image folder **read-only** at `/datasets/project/images`. Raw data are never modified.
- Writes all outputs to `processing/<project_name>/`.
- Reads ODM options from `config/odm_<profile>.args` (commented, one option per line).
- Saves a full timestamped log, including the exact options, to `processing/<project_name>/logs/`.

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
| `--pc-las` | on | Extra `.las` copy of the point cloud. `.laz` is always produced. |

To rerun only later stages (e.g., after changing DEM options), keep the project folder and add `--rerun-from`:

```bash
scripts/run_odm.sh 2026-05-21_Map/Images_Mapping 2026-05-21_Map full --rerun-from odm_dem
```

ODM stage order: `dataset → split → merge → opensfm → openmvs → odm_filterpoints → odm_meshing →
mvs_texturing → odm_georeferencing → odm_dem → odm_orthophoto → odm_report → odm_postprocess`.

### Main outputs (`processing/<project_name>/`)

| Path | Product |
|---|---|
| `odm_orthophoto/odm_orthophoto.tif` | RGB(A) orthomosaic GeoTIFF (COG) |
| `odm_dem/dsm.tif` | Digital Surface Model (m, float32) |
| `odm_dem/dtm.tif` | Digital Terrain Model, bare earth (m, float32) |
| `odm_georeferencing/odm_georeferenced_model.laz` | Classified, georeferenced point cloud |
| `odm_texturing/odm_textured_model_geo.obj` (+ `.glb`) | Textured 3D mesh |
| `odm_report/report.pdf` | QA report: overlap map, GPS residuals, reconstruction stats |
| `opensfm/` , `openmvs/` | Intermediate files (can be deleted after QA; see `--optimize-disk-space`) |

All rasters use the WGS84 / UTM zone CRS ODM picks automatically. For this site that is **UTM 13N, EPSG:32613**.

## 4. Post-processing (GDAL on the host)

```bash
scripts/postprocess.sh processing/2026-05-21_Map 0.5     # 0.5 m contour interval
```

Creates `processing/<project_name>/derived/`:

| File | Description | Rangeland use |
|---|---|---|
| `dtm_hillshade.tif`, `dsm_hillshade.tif` | Multidirectional hillshade | Visualize drainages, erosion, two-tracks, trails |
| `dtm_slope_deg.tif` | Slope (degrees) | Erosion risk, grazing distribution |
| `dtm_color_relief.tif` | Colorized DTM | Quick-look elevation map |
| `chm.tif` | Vegetation height = DSM − DTM, clamped ≥ 0 | Shrub (e.g., sagebrush) height and cover, structure |
| `contours_0.5m.gpkg` | DTM contours | Maps, water flow, layout |
| `summary.txt` | CRS, resolution, extents, elevation stats | Record keeping |
| `quicklooks/*.png` | 1600 px previews (ortho, hillshade, color relief, CHM) | README figures, reports |

## 5. QA checklist

1. **`odm_report/report.pdf`**:
   - Reconstructed images: ideally > 95 % of input images.
   - Overlap map: at least 5 images per point over the area of interest.
   - GPS errors: a few metres is normal without RTK/GCPs.
   - Number of reconstructions: should be 1. More than 1 means a gap split the model.
2. **Orthophoto in QGIS**: look for seamlines, smearing, holes, and ghosted moving objects (livestock, vehicles).
3. **DTM**: hillshade should look smooth. Bumps where shrubs are mean classification left vegetation in. Try tuning `--smrf-threshold` / `--smrf-window`.
4. **CHM**: check heights against a few field-measured shrubs if available.
5. Write run notes (date, ODM version, profile, runtime, issues) in [PROCESSING_LOG.md](PROCESSING_LOG.md).

## 6. Viewing

- **QGIS**: drag in the `.tif`, `.gpkg` and `.laz` files. QGIS 3.18+ shows point clouds natively, with a 3D view.
- **3D model**: open `odm_textured_model_geo.glb` in any glTF viewer, or the `.obj` in MeshLab/Blender.
- **WebODM** (optional GUI): import the same images, or upload the finished `processing/` assets.

## Tuning notes for rangeland

- **Low-contrast grass**: if images fail to match, try `--feature-type sift` (default) with `--min-num-features 15000`, or `--matcher-neighbors 12`.
- **Short-grass sites (DTM ≈ DSM)**: SMRF treats anything under ~0.5 m as ground. On short-grass steppe
  (like 2026-05-21_Map) almost every point becomes ground, so DTM ≈ DSM and the CHM is near zero. That is
  expected behaviour. A drone-photogrammetry CHM is only meaningful for vegetation taller than ~0.3–0.5 m
  (sagebrush, shrubs, trees).
- **Shrubs in the DTM**: lower `--smrf-threshold` (default 0.5 m) to 0.3 m, or raise `--smrf-window` (default 18 m) for larger shrub patches.
- **Edge artifacts**: `--auto-boundary` already crops. Add `--boundary my_area.geojson` for an exact study plot.
- **Memory errors / OOM**: lower `--pc-quality` to `medium`, raise Colima memory, or use `--split 200 --split-overlap 50` (split-merge).
- **Repeat surveys**: add GCPs (`--gcp gcp_list.txt`) or align to the previous survey (`--align previous_model.laz`) so change detection works.
