# Data description

## Dataset: `2026-05-21_Map`

| Item | Value |
|---|---|
| Date | 2026-05-21, 12:49 – 13:38 local time (camera clock) |
| Location | ~41.275° N, 105.669° W (near Laramie, Wyoming, USA) |
| Platform / camera | DJI Air 2S, camera model **FC3411** (XMP `tiff:Model` reads `Test_Pro`) |
| Sensor | 1″ CMOS, 5472 × 3648 px (20 MP), 8.38 mm focal length (22 mm equiv.), f/2.8, rolling shutter |
| Exposure (sample) | 1/120 s, f/2.8, ISO 100 |
| Flight altitude | 60.1 – 61.2 m above takeoff (constant altitude, no terrain following) |
| Takeoff elevation | ~2150 m (EXIF absolute altitude, WGS84 GPS height; not survey-grade) |
| Ground sample distance | ≈ **1.75 cm/px** (sensor 13.2 mm / 5472 px = 2.41 µm pitch × 61 m / 8.38 mm) |
| Image footprint | ≈ 96 m × 64 m per image |
| Covered extent (camera positions) | ≈ 1.13 km E–W × 0.86 km N–S |
| Flight line direction | ≈ 130° / 310° (NW–SE lawnmower pattern) |
| Shot spacing (forward) | median 23 m between consecutive images → **≈ 64 % forward overlap** (64 m along-track footprint) |
| Flight line spacing | 13 lines, median 48 m apart → **≈ 50 % side overlap** (96 m across-track footprint) |
| Gimbal | nadir (pitch −89.8 to −90.0°) |
| Georeferencing | Onboard GNSS only (no RTK, no ground control points) |

### Folders

| Folder | Files | Contents | Used in processing? |
|---|---|---|---|
| `Images_Mapping/` | 494 JPG, 3.6 GB | Nadir mapping photos (`DJI_0350`–`DJI_0846`) | **Yes** |
| `Images_Nav/` | 4 JPG, 23 MB | Ground-level, near-horizontal photos taken at the takeoff point (0 m relative altitude, pitch 0 to −4°). Probably taken at battery swaps. | **No.** They would confuse SfM. |

### Flights (from timestamp gaps)

| Flight | Images | Time | Note |
|---|---|---|---|
| 1 | DJI_0350 – DJI_0637 (288) | 12:51 – 13:06 | Nav photos DJI_0638/0639 taken after landing |
| 2 | DJI_0640 – DJI_0796 (157) | 13:12 – 13:21 | Nav photo DJI_0797 after landing |
| 3 | DJI_0798 – DJI_0846 (49) | 13:33 – 13:38 | Used as the small pipeline test subset |

### Metadata files (tracked in git)

`2026-05-21_Map/metadata/` holds per-image CSV and GeoJSON camera positions produced by
`scripts/inventory_images.py`. Open the `.geojson` files in QGIS to see the flight pattern.

### Overlap caveat

64 % forward / 50 % side overlap is **below the usual recommendation for vegetated
terrain (≈ 75 % / 70 %)**. Grass and shrubs move in the wind and look alike, so they match poorly.
Expect a good orthophoto. DSM/DTM detail between flight lines and at the survey edges will be
weaker. For future flights: raise overlap to 75–80 % / 70 %, or fly higher (e.g., 80–100 m)
at the same overlap settings. Fewer images, better matching, GSD still 2.3–2.9 cm.

## Accuracy expectations

There are **no GCPs and no RTK**, so:

- **Relative accuracy** (inside the map: distances, areas, local height differences such as shrub heights) is good, typically a few cm.
- **Absolute accuracy** (true position on Earth) is set by the drone's GPS: typically **1–3 m horizontal**. Vertically, the raw ODM
  heights for this survey were **40.8 m below NAVD88 with a 13.6 m bowl distortion** (measured against USGS 3DEP).
  After `scripts/correct_dem_3dep.py` the corrected DEMs match 3DEP to **0.12 m RMSE**. See [REPORT.md §5.2](REPORT.md#52-elevation-why-the-corrected-layers-matter).
- For repeat surveys (change detection), either place GCPs or co-register each survey to a reference (e.g., ODM `--align` against an earlier DSM/point cloud).

## Raw data handling

Raw images are **not** stored in git; `.gitignore` excludes `*.JPG`. Keep the original folder as an
archive (external drive, institutional storage, or a data repository such as Zenodo/Dryad) and
record its location here:

- Archive location: _TODO_
- Checksums: SHA-256 of all 498 images in `2026-05-21_Map/metadata/sha256sums.txt`
  (verify with `shasum -a 256 -c 2026-05-21_Map/metadata/sha256sums.txt`)
