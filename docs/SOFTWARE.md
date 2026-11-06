# Software choices

## Selected stack (all open source)

| Component | Role | License | Install (macOS / Apple Silicon) |
|---|---|---|---|
| [OpenDroneMap (ODM)](https://github.com/OpenDroneMap/ODM) 3.6.2 | Photogrammetry engine: structure-from-motion, dense matching, orthophoto, DSM/DTM, mesh | AGPL-3.0 | Docker image `opendronemap/odm:3.6.2` (multi-arch, native arm64) |
| [Colima](https://github.com/abiosoft/colima) | Lightweight Docker runtime VM for macOS | MIT | `brew install colima docker` |
| Docker CLI | Runs the ODM container | Apache-2.0 | (above) |
| [GDAL](https://gdal.org) ≥ 3.11 | Post-processing: hillshade, slope, contours, CHM, COG conversion | MIT | `brew install gdal` |
| [QGIS](https://qgis.org) | Viewing/analysis of GeoTIFFs, contours, point clouds | GPL-2.0 | qgis.org installer or `brew install --cask qgis` |
| Python 3 (stdlib only) | Image metadata inventory | PSF | preinstalled / Homebrew |

Optional:

| Tool | Why you might want it |
|---|---|
| [WebODM](https://github.com/OpenDroneMap/WebODM) | Browser GUI on top of ODM: task management, 2D/3D viewer, measurement tools. Run with `./webodm.sh start` (Docker). Same engine and the same options as the CLI used here. |
| [CloudCompare](https://www.cloudcompare.org) (GPL) | Inspect/compare point clouds (`.laz`), cross-sections, change detection between surveys. |
| [PDAL](https://pdal.io) (BSD) | Scriptable point cloud processing (re-classify ground, filter, rasterize). `brew install pdal`. |
| [MeshLab](https://www.meshlab.net) / [Blender](https://www.blender.org) | Viewing/editing the textured 3D model (`.glb`). |

## Why ODM

- The most complete open-source pipeline that goes from raw drone JPGs to **orthophoto + DSM + DTM + point cloud + textured mesh + QA report** in one command.
- Reads DJI EXIF/XMP GPS and gimbal tags directly, and has built-in **rolling-shutter correction** for the Air 2S.
- Produces standard GIS formats (GeoTIFF/COG, LAZ, GeoPackage), all in a UTM projected CRS.
- The CLI is reproducible: every run here is defined by a profile file in `config/` plus a log.

## Alternatives considered

| Option | Open source? | Notes |
|---|---|---|
| **COLMAP + OpenMVS** | Yes (BSD / AGPL) | Excellent SfM/MVS, but you have to build the georeferencing, orthophoto and DEM steps yourself. ODM already uses OpenSfM + OpenMVS internally. |
| **MicMac** (IGN) | Yes (CeCILL-B) | Very accurate and research-grade. Steep learning curve, slower. Worth considering for high-precision GCP work. |
| **Meshroom** (AliceVision) | Yes (MPL-2) | Aimed at 3D objects, not georeferenced mapping. Needs CUDA for depth maps, which Macs don't have. |
| Agisoft Metashape / Pix4D / DroneDeploy | No (commercial) | Industry standard, polished. Useful as a cross-check if a license is available. |
| WebODM native macOS installer | Paid binary; source is open | Convenient but not necessary. The Docker CLI does the same work. |

## Why Colima (not Docker Desktop)

Docker Desktop requires a paid license for larger organizations. Colima is MIT-licensed, uses Apple's
Virtualization.framework (`--vm-type vz`) with virtiofs file sharing, and runs arm64 containers natively.
Docker Desktop, OrbStack or Podman would work equally well; `scripts/run_odm.sh` only needs a working `docker` command.
