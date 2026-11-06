#!/usr/bin/env bash
# Fine-scale vegetation height for SHORT rangeland vegetation (grass / low shrubs).
#
# ODM's default ground filter (SMRF threshold 0.5 m, window 18 m) treats anything
# lower than ~0.5 m as ground. On short-grass sites that leaves DTM == DSM and CHM == 0.
# This script reclassifies ODM's point cloud with an aggressive SMRF, computes each
# point's height above ground (HAG), and rasterizes vegetation products.
# ODM's own outputs are not modified.
#
# Usage:
#   scripts/vegetation_chm.sh processing/<project_name> [veg_threshold_m] [bounds]
#
#   veg_threshold_m  minimum height counted as vegetation (default 0.10). Below ~0.08 m,
#                    seams between images (a few cm of vertical offset) start to show up.
#   bounds           optional PDAL crop "([xmin,xmax],[ymin,ymax])" for quick tests
#
# Outputs (processing/<project_name>/vegetation/):
#   classified_hag.laz      point cloud: Classification 2=ground / 1=other, + HeightAboveGround
#   chm_10cm.tif            max height above ground per 10 cm cell (m)
#   dtm_fine_10cm.tif       DTM from the fine ground classification (idw, gaps filled)
#   veg_mask_10cm.tif       1 = vegetation (HAG >= threshold), 0 = not
#   veg_cover_1m.tif        fraction of each 1 m cell covered by vegetation (0..1)
#   quicklooks/*.png        previews
#   summary.txt             parameters and statistics
#
# Parameters were tuned on a 200 x 200 m test tile of 2026-05-21_Map
# (see docs/VEGETATION.md for the comparison of 5 filter settings).
set -euo pipefail

PROJ="$(cd "${1:?project dir required}" && pwd)"
THR="${2:-0.10}"
BOUNDS="${3:-}"
ODM_IMAGE="${ODM_IMAGE:-opendronemap/odm:3.6.2}"
PDAL=/code/SuperBuild/install/bin/pdal

# SMRF parameters (fine-scale)
SMRF_THRESHOLD="${SMRF_THRESHOLD:-0.05}"
SMRF_WINDOW="${SMRF_WINDOW:-2}"
SMRF_SLOPE="${SMRF_SLOPE:-0.2}"
SMRF_SCALAR="${SMRF_SCALAR:-1.0}"
RES=0.1

if [[ -z "${DOCKER_HOST:-}" && -S "$HOME/.colima/default/docker.sock" ]]; then
  export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
fi

OUT="$PROJ/vegetation"
mkdir -p "$OUT/quicklooks"
COG=(-of COG -co COMPRESS=DEFLATE -co PREDICTOR=2 -co BIGTIFF=IF_SAFER)

CROP=""
[[ -n "$BOUNDS" ]] && CROP="{\"type\":\"filters.crop\",\"bounds\":\"$BOUNDS\"},"

cat > "$OUT/pipeline.json" <<EOF
[
  "/p/odm_georeferencing/odm_georeferenced_model.laz",
  $CROP
  {"type":"filters.assign","value":"Classification = 1"},
  {"type":"filters.smrf","threshold":$SMRF_THRESHOLD,"window":$SMRF_WINDOW,"slope":$SMRF_SLOPE,"scalar":$SMRF_SCALAR},
  {"type":"filters.hag_nn","count":3},
  {"type":"writers.las","filename":"/p/vegetation/classified_hag.laz","compression":true,
   "extra_dims":"HeightAboveGround=float32","forward":"scale,offset","minor_version":4},
  {"type":"writers.gdal","filename":"/p/vegetation/.chm_raw.tif","dimension":"HeightAboveGround",
   "output_type":"max","resolution":$RES,"nodata":-9999,"data_type":"float32"},
  {"type":"filters.range","limits":"Classification[2:2]"},
  {"type":"writers.gdal","filename":"/p/vegetation/.dtm_raw.tif","dimension":"Z",
   "output_type":"idw","resolution":$RES,"radius":0.3,"window_size":3,"nodata":-9999,"data_type":"float32"}
]
EOF

echo "== PDAL: SMRF (t=$SMRF_THRESHOLD w=$SMRF_WINDOW s=$SMRF_SLOPE k=$SMRF_SCALAR) + HAG"
START=$(date +%s)
docker run --rm -v "$PROJ":/p --entrypoint "$PDAL" "$ODM_IMAGE" pipeline /p/vegetation/pipeline.json
echo "   PDAL took $(( ($(date +%s) - START) / 60 )) min"

echo "== Rasters"
# CHM: clamp tiny negatives to 0
gdal raster reclassify -q --overwrite -m "[-1000,0)=0; NO_DATA=NO_DATA; DEFAULT=PASS_THROUGH" \
  --ot Float32 -i "$OUT/.chm_raw.tif" -o "$OUT/.chm_clamped.tif"
gdal_translate -q "$OUT/.chm_clamped.tif" "$OUT/chm_10cm.tif" "${COG[@]}"

# DTM: fill small holes left where vegetation was removed
gdal raster fill-nodata --overwrite --max-distance 50 --smoothing-iterations 0 \
  -i "$OUT/.dtm_raw.tif" -o "$OUT/.dtm_filled.tif" -q
gdal_translate -q "$OUT/.dtm_filled.tif" "$OUT/dtm_fine_10cm.tif" "${COG[@]}"

# Vegetation mask (HAG >= THR) and 1 m fractional cover
# (strip the -9999 nodata flag via a VRT so it can be mapped to 255 in a Byte raster)
gdal_translate -q -of VRT -a_nodata none "$OUT/chm_10cm.tif" "$OUT/.chm_nonodata.vrt"
gdal raster reclassify -q --overwrite \
  -m "[-10000,-9000]=255; [-1000,$THR)=0; [$THR,1000]=1" --ot UInt8 \
  -i "$OUT/.chm_nonodata.vrt" -o "$OUT/.mask.tif"
gdal_translate -q -a_nodata 255 "$OUT/.mask.tif" "$OUT/veg_mask_10cm.tif" -of COG -co COMPRESS=DEFLATE -co OVERVIEW_RESAMPLING=NEAREST
gdalwarp -q -overwrite -ovr NONE -tr 1 1 -r average -ot Float32 -dstnodata -9999 \
  "$OUT/veg_mask_10cm.tif" "$OUT/.cover.tif"
gdal_translate -q "$OUT/.cover.tif" "$OUT/veg_cover_1m.tif" "${COG[@]}"
rm -f "${OUT:?}"/.chm_raw.tif "${OUT:?}"/.chm_clamped.tif "${OUT:?}"/.dtm_raw.tif "${OUT:?}"/.dtm_filled.tif \
      "${OUT:?}"/.mask.tif "${OUT:?}"/.cover.tif "${OUT:?}"/.chm_nonodata.vrt

echo "== Quick-looks"
Q="$OUT/quicklooks"
printf "nv 255 255 255 0\n0 250 248 240\n0.03 250 248 240\n0.06 200 230 160\n0.12 90 180 70\n0.25 20 110 30\n0.5 0 60 10\n50 0 40 0\n" > "$Q/.chm.txt"
printf "nv 255 255 255 0\n0 250 248 240\n0.05 230 240 200\n0.15 150 200 110\n0.3 60 150 50\n0.6 0 90 20\n1 0 50 10\n" > "$Q/.cover.txt"
gdaldem color-relief -q "$OUT/chm_10cm.tif" "$Q/.chm.txt" "$Q/.chm.tif" -alpha
gdaldem color-relief -q "$OUT/veg_cover_1m.tif" "$Q/.cover.txt" "$Q/.cover.tif" -alpha
gdalwarp -q -overwrite -ts 1600 0 -r max "$Q/.chm.tif" "$Q/.chm_small.tif" && gdal_translate -q -of PNG "$Q/.chm_small.tif" "$Q/chm.png"
gdal_translate -q -of PNG -outsize 1600 0 -r average "$Q/.cover.tif" "$Q/veg_cover.png"
rm -f "${Q:?}"/.chm.* "${Q:?}"/.chm_small.tif "${Q:?}"/.cover.* "${Q:?}"/*.aux.xml

echo "== Summary"
{
  echo "Project:   $PROJ"
  echo "Generated: $(date -Iseconds)"
  echo "SMRF:      threshold=$SMRF_THRESHOLD window=$SMRF_WINDOW slope=$SMRF_SLOPE scalar=$SMRF_SCALAR"
  echo "Veg threshold (HAG): $THR m   Raster resolution: $RES m"
  [[ -n "$BOUNDS" ]] && echo "Bounds:    $BOUNDS"
  for f in chm_10cm veg_cover_1m dtm_fine_10cm; do
    echo "--- $f"
    gdalinfo -stats "$OUT/$f.tif" 2>/dev/null | grep -E "STATISTICS_(MINIMUM|MAXIMUM|MEAN|STDDEV|VALID_PERCENT)" | sort -u
    rm -f "$OUT/$f.tif.aux.xml"
  done
  echo "(veg_cover_1m MEAN = overall fraction of the mapped area covered by vegetation >= $THR m)"
} | tee "$OUT/summary.txt"
