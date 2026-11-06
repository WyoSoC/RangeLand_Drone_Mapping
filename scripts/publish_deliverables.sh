#!/usr/bin/env bash
# Zip a survey's deliverables and upload the zip + SHA-256 checksum to the public download server.
#
# Usage:
#   scripts/publish_deliverables.sh <survey>            e.g. scripts/publish_deliverables.sh 2026-05-21_Map
#
# Creates  deliverables/RangeLand_<survey>_deliverables.zip (+ .sha256)
# Uploads  to $REMOTE_HOST:$REMOTE_DIR/ (default: datahive, the Tailscale Funnel folder)
# Public   $PUBLIC_URL/RangeLand_<survey>_deliverables.zip
#
# Files are stored uncompressed (zip -0): GeoTIFF/LAZ/GLB are already compressed internally.
# The archive uses Zip64 (> 4 GB). It opens with macOS Archive Utility, Windows Explorer, 7-Zip and `unzip`.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
S="${1:?survey name required}"
REMOTE_HOST="${REMOTE_HOST:-datahive}"
REMOTE_DIR="${REMOTE_DIR:-/mnt/datahive/Data/DeweyData_Filtered/RangeLand_DroneMaps}"
PUBLIC_URL="${PUBLIC_URL:-https://datahive.echo-tint.ts.net/RangeLand_DroneMaps}"

cd "$REPO/deliverables"
[[ -d "$S" ]] || { echo "No deliverables/$S (run make_deliverables.sh first)" >&2; exit 1; }
Z="RangeLand_${S}_deliverables.zip"

echo "== Zipping deliverables/$S -> $Z"
rm -f "$Z" "$Z.sha256"
zip -r -0 -X -q "$Z" "$S" -x '*.DS_Store'
unzip -tq "$Z"
shasum -a 256 "$Z" > "$Z.sha256"
cat "$Z.sha256"

echo "== Uploading to $REMOTE_HOST:$REMOTE_DIR"
ssh "$REMOTE_HOST" "mkdir -p '$REMOTE_DIR'"
rsync -a --partial "$Z" "$Z.sha256" "$REMOTE_HOST:$REMOTE_DIR/"
ssh "$REMOTE_HOST" "cd '$REMOTE_DIR' && sha256sum -c '$Z.sha256'"

echo "== Checking public URL"
LEN=$(curl -sfI "$PUBLIC_URL/$Z" | awk 'tolower($1)=="content-length:"{print $2}' | tr -d '\r')
[[ "$LEN" == "$(stat -f %z "$Z" 2>/dev/null || stat -c %s "$Z")" ]] \
  && echo "OK: $PUBLIC_URL/$Z ($LEN bytes)" \
  || { echo "Public URL check failed (got length '$LEN')" >&2; exit 1; }
