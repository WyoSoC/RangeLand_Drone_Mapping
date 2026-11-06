#!/usr/bin/env bash
# Export a thin slice of the classified point cloud to CSV (for cross-section plots).
#
# Usage:
#   scripts/export_section.sh processing/<project> <name> <xmin> <xmax> <ymin> <ymax>
#
# Reads  processing/<project>/vegetation/classified_hag.laz (from vegetation_chm.sh)
# Writes processing/<project>/vegetation/sections/<name>.csv  (X,Y,Z,Classification,HeightAboveGround,R,G,B)
#
# Slices used in docs/REPORT.md (Figure 10):
#   scripts/export_section.sh processing/2026-05-21_Map veg  444000 444030 4569450.8 4569451.2
#   scripts/export_section.sh processing/2026-05-21_Map band 444040 444070 4569686.8 4569687.2
set -euo pipefail
PROJ="$(cd "${1:?project dir}" && pwd)"; NAME="${2:?name}"
XMIN="$3"; XMAX="$4"; YMIN="$5"; YMAX="$6"
ODM_IMAGE="${ODM_IMAGE:-opendronemap/odm:3.6.2}"
if [[ -z "${DOCKER_HOST:-}" && -S "$HOME/.colima/default/docker.sock" ]]; then
  export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
fi
mkdir -p "$PROJ/vegetation/sections"
cat > "$PROJ/vegetation/sections/$NAME.json" <<EOF
[
  {"type":"readers.las","filename":"/p/vegetation/classified_hag.laz","extra_dims":"HeightAboveGround=float32"},
  {"type":"filters.crop","bounds":"([$XMIN,$XMAX],[$YMIN,$YMAX])"},
  {"type":"writers.text","filename":"/p/vegetation/sections/$NAME.csv",
   "order":"X,Y,Z,Classification,HeightAboveGround,Red,Green,Blue","keep_unspecified":false}
]
EOF
docker run --rm -v "$PROJ":/p --entrypoint /code/SuperBuild/install/bin/pdal "$ODM_IMAGE" \
  pipeline "/p/vegetation/sections/$NAME.json"
echo "wrote $PROJ/vegetation/sections/$NAME.csv ($(($(wc -l < "$PROJ/vegetation/sections/$NAME.csv") - 1)) points)"
