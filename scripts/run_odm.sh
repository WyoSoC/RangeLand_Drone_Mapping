#!/usr/bin/env bash
# Run OpenDroneMap (Docker) on a folder of mapping images.
#
# Usage:
#   scripts/run_odm.sh <image_dir> <project_name> [profile] [extra ODM args...]
#
#   image_dir     folder of JPGs (mounted read-only; never modified)
#   project_name  output goes to processing/<project_name>/
#   profile       name of config/odm_<profile>.args (default: full)
#
# Examples:
#   scripts/run_odm.sh 2026-05-21_Map/Images_Mapping 2026-05-21_Map full
#   scripts/run_odm.sh /path/to/subset test_flight3 preview
#   scripts/run_odm.sh 2026-05-21_Map/Images_Mapping 2026-05-21_Map full --rerun-from odm_dem
#
# Environment overrides:
#   ODM_IMAGE   docker image   (default opendronemap/odm:3.6.2)
#   ODM_OUT     output root    (default <repo>/processing)
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
IMG_DIR="${1:?image_dir required}"
NAME="${2:?project_name required}"
PROFILE="${3:-full}"
shift $(( $# >= 3 ? 3 : $# ))
EXTRA=("$@")

ODM_IMAGE="${ODM_IMAGE:-opendronemap/odm:3.6.2}"
OUT_ROOT="${ODM_OUT:-$REPO/processing}"
ARGS_FILE="$REPO/config/odm_${PROFILE}.args"

[[ -d "$IMG_DIR" ]] || { echo "No such image dir: $IMG_DIR" >&2; exit 1; }
[[ -f "$ARGS_FILE" ]] || { echo "No such profile: $ARGS_FILE" >&2; exit 1; }
IMG_DIR="$(cd "$IMG_DIR" && pwd)"

# Use Colima's socket automatically if DOCKER_HOST isn't set and Colima is running.
if [[ -z "${DOCKER_HOST:-}" && -S "$HOME/.colima/default/docker.sock" ]]; then
  export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
fi

# Profile file: one or more args per line, '#' comments allowed.
mapfile_compat() { grep -vE '^\s*(#|$)' "$1" | sed 's/#.*//' | tr -s ' \t' '\n' | grep -v '^$'; }
PROFILE_ARGS=()
while IFS= read -r a; do PROFILE_ARGS+=("$a"); done < <(mapfile_compat "$ARGS_FILE")

PROJ="$OUT_ROOT/$NAME"
mkdir -p "$PROJ/images" "$PROJ/logs"
LOG="$PROJ/logs/odm_$(date +%Y%m%d_%H%M%S).log"
N_IMG=$(find "$IMG_DIR" -maxdepth 1 -iname '*.jp*g' | wc -l | tr -d ' ')

{
  echo "# ODM run $(date -Iseconds)"
  echo "# image:    $ODM_IMAGE"
  echo "# images:   $IMG_DIR ($N_IMG files)"
  echo "# project:  $PROJ"
  echo "# profile:  $ARGS_FILE"
  echo "# args:     ${PROFILE_ARGS[*]} ${EXTRA[*]:-}"
} | tee "$LOG"

# Images are mounted read-only on top of the project's images/ folder,
# so ODM's outputs land in processing/<name>/ and raw data stay untouched.
time docker run --rm \
  -v "$PROJ":/datasets/project \
  -v "$IMG_DIR":/datasets/project/images:ro \
  "$ODM_IMAGE" \
  --project-path /datasets project \
  "${PROFILE_ARGS[@]}" ${EXTRA[@]+"${EXTRA[@]}"} 2>&1 | tee -a "$LOG"

echo "Done. Outputs in $PROJ  (log: $LOG)"
