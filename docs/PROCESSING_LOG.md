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
- **Runtime:** _running_
- **Result:** _pending_

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
