#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "${ROOT_DIR}/scripts/config.sh"

IMAGE=${IMAGE:-hikmicro_thermal_ros2:jetson}
DISPLAY_VALUE=${DISPLAY:-:0}
XAUTHORITY_VALUE=${XAUTHORITY:-$HOME/.Xauthority}
THERMAL_TOPIC=${THERMAL_TOPIC:-/fanet/input/thermal}
OVERLAY_TOPIC=${OVERLAY_TOPIC:-/fanet/segmentation/overlay}

docker rm -f fanet_viewer_overlay fanet_viewer_thermal >/dev/null 2>&1 || true

common_args=(
  --rm
  -d
  --network host
  --ipc host
  --pid host
  --privileged
  -e ROS_DOMAIN_ID=${ROS_DOMAIN_ID}
  -e RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION}
  -e DISPLAY=${DISPLAY_VALUE}
)

if [[ -d /tmp/.X11-unix ]]; then
  common_args+=( -v /tmp/.X11-unix:/tmp/.X11-unix:rw )
fi

if [[ -f "${XAUTHORITY_VALUE}" ]]; then
  common_args+=( -e XAUTHORITY=${XAUTHORITY_VALUE} -v "${XAUTHORITY_VALUE}:${XAUTHORITY_VALUE}:ro" )
fi

docker run "${common_args[@]}" \
  --name fanet_viewer_thermal \
  "${IMAGE}" \
  bash -lc "source /opt/ros/humble/install/setup.bash && ros2 run image_view image_view --ros-args -r image:=${THERMAL_TOPIC}"

docker run "${common_args[@]}" \
  --name fanet_viewer_overlay \
  "${IMAGE}" \
  bash -lc "source /opt/ros/humble/install/setup.bash && ros2 run image_view image_view --ros-args -r image:=${OVERLAY_TOPIC}"

echo "Visores lanzados:"
echo "  Termica : ${THERMAL_TOPIC} (contenedor fanet_viewer_thermal)"
echo "  Overlay : ${OVERLAY_TOPIC} (contenedor fanet_viewer_overlay)"
echo "Para cerrarlos: docker rm -f fanet_viewer_overlay fanet_viewer_thermal"