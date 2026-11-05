# RangeLand DroneMaps

Reproducible, open-source photogrammetry workflow that turns drone survey photos of rangeland into
**orthomosaic GeoTIFFs, digital surface and terrain models (DSM/DTM), vegetation height models,
contours, classified point clouds and textured 3D models**.

Engine: [OpenDroneMap](https://github.com/OpenDroneMap/ODM) (Docker), post-processing with [GDAL](https://gdal.org),
viewing in [QGIS](https://qgis.org). Tested on macOS / Apple Silicon (M1 Max, 64 GB).

## Quick start

```bash
# one-time setup
brew install colima docker gdal
colima start --cpu 8 --memory 48 --disk 300 --arch aarch64 --vm-type vz --mount-type virtiofs
docker pull opendronemap/odm:3.6.2

# 1. inventory / QA of the images
python3 scripts/inventory_images.py 2026-05-21_Map/Images_Mapping

# 2. photogrammetry (orthophoto, DSM, DTM, point cloud, 3D model, report)
scripts/run_odm.sh 2026-05-21_Map/Images_Mapping 2026-05-21_Map full

# 3. derived products (hillshade, slope, contours, canopy height model)
scripts/postprocess.sh processing/2026-05-21_Map 0.5
```

## Repository layout

```
.
├── README.md
├── docs/
│   ├── WORKFLOW.md          # step-by-step processing guide (start here)
│   ├── DATA.md              # dataset description, flight parameters, accuracy notes
│   ├── SOFTWARE.md          # tool choices, licenses, alternatives
│   └── PROCESSING_LOG.md    # record of every processing run and its results
├── config/
│   ├── odm_full.args        # full-quality ODM profile (commented)
│   ├── odm_test.args        # reduced-quality end-to-end test profile
│   └── odm_preview.args     # fast-orthophoto preview profile
├── scripts/
│   ├── inventory_images.py  # EXIF/XMP inventory, flight summary, camera GeoJSON (stdlib only)
│   ├── run_odm.sh           # runs ODM in Docker with a profile; logs everything
│   └── postprocess.sh       # GDAL: hillshade, slope, color relief, CHM, contours, summary
├── 2026-05-21_Map/          # one folder per survey
│   ├── Images_Mapping/      # raw nadir images (NOT in git)
│   ├── Images_Nav/          # ground-level takeoff photos (NOT in git, not processed)
│   └── metadata/            # inventory CSV, camera GeoJSON, SHA-256 checksums (in git)
└── processing/              # ODM outputs (NOT in git; regenerable)
```

## Surveys

| Survey | Drone / camera | Images | Altitude | GSD | Area | Status |
|---|---|---|---|---|---|---|
| [2026-05-21_Map](docs/DATA.md) | DJI Air 2S (FC3411) | 494 nadir | 61 m AGL | 1.75 cm | ~1.1 × 0.9 km | see [PROCESSING_LOG](docs/PROCESSING_LOG.md) |

## Adding a new survey

1. Create `YYYY-MM-DD_<Name>/Images_Mapping/` and copy in **only nadir mapping images**.
2. `python3 scripts/inventory_images.py YYYY-MM-DD_<Name>/Images_Mapping -o .../metadata/inventory.csv --geojson .../metadata/cameras.geojson`
3. `scripts/run_odm.sh YYYY-MM-DD_<Name>/Images_Mapping YYYY-MM-DD_<Name> full`
4. `scripts/postprocess.sh processing/YYYY-MM-DD_<Name>`
5. Add a section to `docs/DATA.md` and an entry to `docs/PROCESSING_LOG.md`.

## Data and outputs

Raw imagery (3.6 GB for this survey) and processing outputs (tens of GB) are excluded from git
(see `.gitignore`). Archive them separately, e.g. on institutional storage, Zenodo or an S3 bucket. Checksums
are tracked in `*/metadata/sha256sums.txt`. Use [Git LFS](https://git-lfs.com) or a GitHub Release if you
want to publish small final products such as a downsampled orthophoto.

## License

Code and documentation in this repository: MIT (see `LICENSE`). OpenDroneMap is AGPL-3.0 and is
used unmodified as a Docker container.
