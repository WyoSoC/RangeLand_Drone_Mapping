#!/usr/bin/env bash
# Create the glTF binary (.glb) 3D model for an ODM project that was processed without --gltf.
# Uses ODM's own converter (opendm.gltf.obj2glb), exactly as `--gltf` would, without rerunning any stage.
#
# Usage:
#   scripts/make_glb.sh processing/<project_name>
#
# Reads  odm_texturing/odm_textured_model_geo.obj (+ .mtl and textures)
#        odm_georeferencing/coords.txt (UTM offset, line 2)
# Writes odm_texturing/odm_textured_model_geo.glb
#        (Draco-compressed mesh, JPEG textures, CESIUM_RTC centre = UTM offset)
set -euo pipefail
PROJ="$(cd "${1:?project dir required}" && pwd)"
ODM_IMAGE="${ODM_IMAGE:-opendronemap/odm:3.6.2}"
if [[ -z "${DOCKER_HOST:-}" && -S "$HOME/.colima/default/docker.sock" ]]; then
  export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"
fi
read -r OX OY < <(sed -n 2p "$PROJ/odm_georeferencing/coords.txt")
echo "UTM offset: $OX $OY"
docker run --rm -v "$PROJ":/p -w /code --entrypoint python3 "$ODM_IMAGE" -c "
import sys; sys.path.insert(0, '/code')
from opendm.gltf import obj2glb
obj2glb('/p/odm_texturing/odm_textured_model_geo.obj', '/p/odm_texturing/odm_textured_model_geo.glb',
        rtc=($OX, $OY), draco_compression=True)
"
ls -lh "$PROJ/odm_texturing/odm_textured_model_geo.glb"
