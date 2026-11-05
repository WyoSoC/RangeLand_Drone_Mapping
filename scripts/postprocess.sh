#!/usr/bin/env bash
# Derive analysis products from ODM outputs using GDAL (runs on the host).
#
# Usage:
#   scripts/postprocess.sh processing/<project_name> [contour_interval_m]
#
# Creates processing/<project_name>/derived/:
#   dtm_hillshade.tif      shaded relief of bare-earth terrain
#   dsm_hillshade.tif      shaded relief of surface (vegetation, objects)
#   dtm_slope_deg.tif      terrain slope in degrees
#   dtm_color_relief.tif   colorized DTM (RGB) for quick visual use
#   chm.tif                canopy/vegetation height model = DSM - DTM (m, clamped >= 0)
#   contours_<N>m.gpkg     terrain contours from DTM (GeoPackage)
#   summary.txt            CRS, resolution, extents, elevation stats
#   quicklooks/*.png       small (1600 px) previews for docs/README
#
# Needs GDAL >= 3.11 (uses `gdal raster reclassify`) and python3 (stdlib only).
set -euo pipefail

PROJ="${1:?project dir required, e.g. processing/2026-05-21_Map}"
INTERVAL="${2:-0.5}"
DEM="$PROJ/odm_dem"
ORTHO="$PROJ/odm_orthophoto/odm_orthophoto.tif"
OUT="$PROJ/derived"
mkdir -p "$OUT"

DSM="$DEM/dsm.tif"
DTM="$DEM/dtm.tif"
COG=(-of COG -co COMPRESS=DEFLATE -co PREDICTOR=2 -co BIGTIFF=IF_SAFER)

have() { [[ -f "$1" ]]; }

if have "$DTM"; then
  echo "== DTM products"
  gdaldem hillshade "$DTM" "$OUT/dtm_hillshade.tif" -multidirectional -compute_edges "${COG[@]}" -q
  gdaldem slope     "$DTM" "$OUT/dtm_slope_deg.tif" -compute_edges "${COG[@]}" -q

  # Color relief ramp stretched to the DTM's own 2nd..98th percentile-ish range (min/max here).
  read -r ZMIN ZMAX < <(gdalinfo -stats "$DTM" 2>/dev/null \
      | awk -F= '/STATISTICS_MINIMUM/{mn=$2} /STATISTICS_MAXIMUM/{mx=$2} END{print mn, mx}')
  rm -f "$DTM.aux.xml"
  RAMP="$OUT/.ramp.txt"
  awk -v a="$ZMIN" -v b="$ZMAX" 'BEGIN{
    d=b-a; printf "nv 0 0 0 0\n";
    printf "%f 43 131 186\n%f 171 221 164\n%f 255 255 191\n%f 253 174 97\n%f 215 25 28\n",
      a, a+0.25*d, a+0.5*d, a+0.75*d, b }' > "$RAMP"
  gdaldem color-relief "$DTM" "$RAMP" "$OUT/dtm_color_relief.tif" -alpha "${COG[@]}" -q
  rm -f "$RAMP"

  echo "== Contours every ${INTERVAL} m"
  rm -f "$OUT/contours_${INTERVAL}m.gpkg"
  gdal_contour -q -a elev_m -i "$INTERVAL" -f GPKG "$DTM" "$OUT/contours_${INTERVAL}m.gpkg"
fi

if have "$DSM"; then
  echo "== DSM hillshade"
  gdaldem hillshade "$DSM" "$OUT/dsm_hillshade.tif" -multidirectional -compute_edges "${COG[@]}" -q
fi

if have "$DSM" && have "$DTM"; then
  echo "== Canopy height model (DSM - DTM)"
  # 1) Put the DTM exactly on the DSM grid (extents can differ slightly).
  # 2) DSM - DTM with a VRT "diff" pixel function. This works in every GDAL build;
  #    `gdal raster calc` needs muparser, which Homebrew's GDAL lacks.
  # 3) Clamp negative heights (DTM interpolation noise) to 0 with `gdal raster reclassify`.
  ABS_DSM="$(cd "$(dirname "$DSM")" && pwd)/$(basename "$DSM")"
  ABS_OUT="$(cd "$OUT" && pwd)"
  GRID=$(gdalinfo -json "$DSM" | python3 -c '
import json,sys; d=json.load(sys.stdin); gt=d["geoTransform"]; w,h=d["size"]
print(gt[0], gt[3]+gt[5]*h, gt[0]+gt[1]*w, gt[3], gt[1], w, h)')
  read -r XMIN YMIN XMAX YMAX RES W H <<< "$GRID"
  gdalwarp -q -overwrite -te "$XMIN" "$YMIN" "$XMAX" "$YMAX" -ts "$W" "$H" -r bilinear \
           -dstnodata -9999 -co COMPRESS=DEFLATE -co BIGTIFF=IF_SAFER "$DTM" "$ABS_OUT/.dtm_on_dsm.tif"
  HEADER=$(gdalinfo -json "$DSM" | python3 -c '
import json,sys
from xml.sax.saxutils import escape
d=json.load(sys.stdin)
print("<SRS>%s</SRS><GeoTransform>%s</GeoTransform>" % (escape(d["coordinateSystem"]["wkt"]), ", ".join(map(str, d["geoTransform"]))))')
  cat > "$ABS_OUT/.chm.vrt" <<EOF
<VRTDataset rasterXSize="$W" rasterYSize="$H">
  $HEADER
  <VRTRasterBand dataType="Float32" band="1" subClass="VRTDerivedRasterBand">
    <NoDataValue>-9999</NoDataValue>
    <PixelFunctionType>diff</PixelFunctionType>
    <PixelFunctionArguments propagateNoData="true"/>
    <SimpleSource><SourceFilename relativeToVRT="0">$ABS_DSM</SourceFilename><SourceBand>1</SourceBand></SimpleSource>
    <SimpleSource><SourceFilename relativeToVRT="0">$ABS_OUT/.dtm_on_dsm.tif</SourceFilename><SourceBand>1</SourceBand></SimpleSource>
  </VRTRasterBand>
</VRTDataset>
EOF
  gdal raster reclassify -q --overwrite -m "[-1000,0)=0; NO_DATA=NO_DATA; DEFAULT=PASS_THROUGH" \
    --ot Float32 -i "$ABS_OUT/.chm.vrt" -o "$ABS_OUT/.chm_raw.tif"
  gdal_translate -q "$ABS_OUT/.chm_raw.tif" "$OUT/chm.tif" "${COG[@]}"
  rm -f "$ABS_OUT/.dtm_on_dsm.tif" "$ABS_OUT/.chm_raw.tif" "$ABS_OUT/.chm.vrt"
fi

echo "== Quick-look PNGs"
QL="$OUT/quicklooks"; mkdir -p "$QL"
ql() { have "$1" && gdal_translate -q -of PNG -outsize 1600 0 -r average "$1" "$QL/$2.png" && rm -f "$QL/$2.png.aux.xml"; }
ql "$ORTHO" orthophoto || true
ql "$OUT/dtm_hillshade.tif" dtm_hillshade || true
ql "$OUT/dtm_color_relief.tif" dtm_color_relief || true
if have "$OUT/chm.tif"; then
  # vegetation height: 0 m light tan -> 0.5 m green -> >= 2 m dark green
  printf "nv 0 0 0 0\n0 245 240 225\n0.5 120 190 90\n2 0 90 30\n100 0 60 20\n" > "$QL/.chm_ramp.txt"
  gdaldem color-relief "$OUT/chm.tif" "$QL/.chm_ramp.txt" "$QL/.chm_rgb.tif" -alpha -q
  ql "$QL/.chm_rgb.tif" chm || true
  rm -f "$QL/.chm_ramp.txt" "$QL/.chm_rgb.tif"
fi

echo "== Summary"
{
  echo "Project: $PROJ"
  echo "Generated: $(date -Iseconds)"
  for f in "$ORTHO" "$DSM" "$DTM" "$OUT/chm.tif"; do
    have "$f" || continue
    echo
    echo "--- $(basename "$f")"
    gdalinfo -stats "$f" 2>/dev/null | grep -E "^Size is|Pixel Size|ID\[\"EPSG\",[0-9]+\]\]$|STATISTICS_(MINIMUM|MAXIMUM|MEAN|STDDEV)" \
      | sed -n '1,12p'
    gdalinfo "$f" | grep -A4 "^Corner Coordinates" | sed -n '2,5p'
    rm -f "$f.aux.xml"
  done
} | tee "$OUT/summary.txt"

echo "Derived products in $OUT"
