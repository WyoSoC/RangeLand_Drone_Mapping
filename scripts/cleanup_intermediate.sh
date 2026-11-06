#!/usr/bin/env bash
# Delete ODM's intermediate files for a survey once QA is done and deliverables are copied.
# Frees most of the disk space (for 2026-05-21_Map: 75 GB -> 13 GB). Final products, the vegetation and
# terrain layers used by the QGIS project, reference data and logs are kept.
# After this, ODM can't `--rerun-from` a later stage. Reprocessing needs a full run from the raw photos.
#
# Usage:
#   scripts/cleanup_intermediate.sh <survey>          # dry run: list what would be deleted
#   scripts/cleanup_intermediate.sh <survey> --yes    # delete
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
S="${1:?survey name required}"
W="$REPO/processing/${S:?}"
[[ -d "$W" ]] || { echo "No working folder $W" >&2; exit 1; }

TARGETS=(
  "$W/opensfm" "$W/openmvs" "$W/odm_filterpoints" "$W/odm_meshing" "$W/odm_texturing_25d"
  "$W/odm_georeferencing/odm_georeferenced_model.las"
  "$W/odm_orthophoto/odm_orthophoto.original.tif"
  "$W/odm_dem/dsm.original.tif" "$W/odm_dem/dtm.original.tif"
  "$W/vegetation/test" "$W/vegetation/test_tile"
)
found=()
for t in "${TARGETS[@]}"; do [[ -e "$t" ]] && found+=("$t"); done
if (( ${#found[@]} == 0 )); then echo "Nothing to delete."; exit 0; fi
du -sh "${found[@]}"
if [[ "${2:-}" == "--yes" ]]; then
  rm -rf -- "${found[@]}"
  echo "Deleted. Working folder now: $(du -sh "$W" | cut -f1)"
else
  echo "(dry run: add --yes to delete)"
fi
