#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "${ROOT_DIR}/scripts/config.sh"
IMAGE=${IMAGE:-hikmicro_thermal_ros2:jetson}
DISPLAY_VALUE=${DISPLAY:-:0}
XAUTHORITY_VALUE=${XAUTHORITY:-$HOME/.Xauthority}
GUI_TOPIC=${GUI_TOPIC:-${FANET_GUI_RGB_TOPIC}}

docker rm -f fanet_person_overlay >/dev/null 2>&1 || true

DOCKER_ARGS=(
  --rm
  -d
  --name fanet_person_overlay
  --network host
  --ipc host
  --pid host
  --privileged
  -e ROS_DOMAIN_ID=${ROS_DOMAIN_ID}
  -e RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION}
  -e DISPLAY=${DISPLAY_VALUE}
  -v "${ROOT_DIR}:/workspace/deploy:ro"
)

if [[ -d /tmp/.X11-unix ]]; then
  DOCKER_ARGS+=( -v /tmp/.X11-unix:/tmp/.X11-unix:rw )
fi

if [[ -f "${XAUTHORITY_VALUE}" ]]; then
  DOCKER_ARGS+=( -e XAUTHORITY=${XAUTHORITY_VALUE} -v "${XAUTHORITY_VALUE}:${XAUTHORITY_VALUE}:ro" )
fi

docker run "${DOCKER_ARGS[@]}" \
  "${IMAGE}" \
  bash -lc "source /opt/ros/humble/install/setup.bash && python3 /workspace/deploy/image_topic_viewer.py --topic ${GUI_TOPIC} --window-name fanet_person_overlay"

echo "Visor GUI lanzado en contenedor fanet_person_overlay sobre ${GUI_TOPIC}"
echo "Para cerrarlo: docker rm -f fanet_person_overlay"