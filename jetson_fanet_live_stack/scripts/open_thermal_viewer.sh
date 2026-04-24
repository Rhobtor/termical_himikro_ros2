#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "${ROOT_DIR}/scripts/config.sh"

IMAGE=${IMAGE:-hikmicro_thermal_ros2:jetson}
DISPLAY_VALUE=${DISPLAY:-:0}
XAUTHORITY_VALUE=${XAUTHORITY:-$HOME/.Xauthority}
THERMAL_TOPIC=${THERMAL_TOPIC:-/fanet/raw/thermal}
VIEWER_NAME=${VIEWER_NAME:-fanet_viewer_thermal_only}
COLORIZE_THERMAL=${COLORIZE_THERMAL:-1}

docker rm -f "${VIEWER_NAME}" >/dev/null 2>&1 || true

docker_args=(
  --rm
  -d
  --name "${VIEWER_NAME}"
  --network host
  --ipc host
  --pid host
  --privileged
  -e ROS_DOMAIN_ID=${ROS_DOMAIN_ID}
  -e RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION}
  -e DISPLAY=${DISPLAY_VALUE}
)

if [[ -d /tmp/.X11-unix ]]; then
  docker_args+=( -v /tmp/.X11-unix:/tmp/.X11-unix:rw )
fi

if [[ -f "${XAUTHORITY_VALUE}" ]]; then
  docker_args+=( -e XAUTHORITY=${XAUTHORITY_VALUE} -v "${XAUTHORITY_VALUE}:${XAUTHORITY_VALUE}:ro" )
fi

colorize_flag=""
if [[ "${COLORIZE_THERMAL}" == "1" ]]; then
  colorize_flag="--colorize"
fi

docker run "${docker_args[@]}" \
  -v "${ROOT_DIR}:/workspace/deploy:ro" \
  "${IMAGE}" \
  bash -lc "source /opt/ros/humble/install/setup.bash && python3 /workspace/deploy/thermal_topic_viewer.py --topic ${THERMAL_TOPIC} --window-name ${VIEWER_NAME} ${colorize_flag}"

echo "Visor termico lanzado: ${THERMAL_TOPIC} (contenedor ${VIEWER_NAME})"
echo "Para cerrarlo: docker rm -f ${VIEWER_NAME}"