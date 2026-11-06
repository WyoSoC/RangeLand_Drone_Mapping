#!/usr/bin/env bash
# Copy the final mapping products of a survey into deliverables/<survey>/ with descriptive names.
#
# Usage:
#   scripts/make_deliverables.sh <survey>        e.g. scripts/make_deliverables.sh 2026-05-21_Map
#
# Expects the outputs of run_odm.sh, vegetation_chm.sh, correct_dem_3dep.py, postprocess.sh (corrected DEMs,
# OUT=.../derived_navd88) and make_glb.sh (or --gltf). Missing products are reported and skipped.
# On APFS (macOS) files are cloned (cp -c): instant, no extra disk space until modified.
# Write deliverables/<survey>/README.txt yourself (see the 2026-05-21_Map one as a template).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
S="${1:?survey name required}"
SRC="$REPO/processing/$S"
DST="$REPO/deliverables/$S"
P="${S%%_*}"   # date prefix, e.g. 2026-05-21
[[ -d "$SRC" ]] || { echo "No working folder $SRC" >&2; exit 1; }
mkdir -p "$DST"

while read -r src dst; do
  if [[ -f "$SRC/$src" ]]; then
    cp -c "$SRC/$src" "$DST/$dst" 2>/dev/null || cp "$SRC/$src" "$DST/$dst"
    cmp -s "$SRC/$src" "$DST/$dst" && printf "  ok       %s\n" "$dst" || printf "  MISMATCH %s\n" "$dst"
  else
    printf "  missing  %s  (expected %s)\n" "$dst" "$src"
  fi
done <<EOF
odm_orthophoto/odm_orthophoto.tif           ${P}_orthophoto_2cm.tif
corrected/dtm_navd88.tif                    ${P}_DTM_5cm_NAVD88.tif
corrected/dsm_navd88.tif                    ${P}_DSM_5cm_NAVD88.tif
derived_navd88/contours_0.25m.gpkg          ${P}_contours_0.25m_NAVD88.gpkg
derived_navd88/dtm_slope_deg_1m.tif         ${P}_slope_1m_degrees.tif
vegetation/veg_cover_1m.tif                 ${P}_vegetation_cover_1m.tif
vegetation/classified_hag.laz               ${P}_point_cloud_classified_HAG.laz
odm_texturing/odm_textured_model_geo.glb    ${P}_3D_model_textured.glb
odm_report/report.pdf                       ${P}_ODM_quality_report.pdf
EOF
du -sh "$DST"
