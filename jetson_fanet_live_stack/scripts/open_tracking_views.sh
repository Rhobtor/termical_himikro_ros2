#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "${ROOT_DIR}/scripts/config.sh"

IMAGE=${IMAGE:-hikmicro_thermal_ros2:jetson}
DISPLAY_VALUE=${DISPLAY:-:0}
XAUTHORITY_VALUE=${XAUTHORITY:-$HOME/.Xauthority}

ANNOTATED_TOPIC=${ANNOTATED_TOPIC:-${FANET_GUI_RGB_TOPIC}}
THERMAL_TOPIC=${THERMAL_TOPIC:-${FANET_RAW_THERMAL_TOPIC}}
ZED_TOPIC=${ZED_TOPIC:-${ZED_RGB_TOPIC}}

docker rm -f fanet_view_rgb_annotated fanet_view_thermal_original fanet_view_zed_original >/dev/null 2>&1 || true

COMMON_ARGS=(
  --rm
  -d
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
  COMMON_ARGS+=( -v /tmp/.X11-unix:/tmp/.X11-unix:rw )
fi

if [[ -f "${XAUTHORITY_VALUE}" ]]; then
  COMMON_ARGS+=( -e XAUTHORITY=${XAUTHORITY_VALUE} -v "${XAUTHORITY_VALUE}:${XAUTHORITY_VALUE}:ro" )
fi

docker run "${COMMON_ARGS[@]}" \
  --name fanet_view_rgb_annotated \
  "${IMAGE}" \
  bash -lc "source /opt/ros/humble/install/setup.bash && python3 /workspace/deploy/image_topic_viewer.py --topic ${ANNOTATED_TOPIC} --window-name fanet_rgb_annotated"

docker run "${COMMON_ARGS[@]}" \
  --name fanet_view_zed_original \
  "${IMAGE}" \
  bash -lc "source /opt/ros/humble/install/setup.bash && python3 /workspace/deploy/image_topic_viewer.py --topic ${ZED_TOPIC} --window-name fanet_zed_original"

docker run "${COMMON_ARGS[@]}" \
  --name fanet_view_thermal_original \
  "${IMAGE}" \
  bash -lc "source /opt/ros/humble/install/setup.bash && python3 /workspace/deploy/thermal_topic_viewer.py --topic ${THERMAL_TOPIC} --window-name fanet_thermal_original --colorize"

echo "Visores lanzados:"
echo "  RGB anotada : ${ANNOTATED_TOPIC} (fanet_view_rgb_annotated)"
echo "  ZED original: ${ZED_TOPIC} (fanet_view_zed_original)"
echo "  Termica orig: ${THERMAL_TOPIC} (fanet_view_thermal_original)"
echo "Para cerrarlos: docker rm -f fanet_view_rgb_annotated fanet_view_thermal_original fanet_view_zed_original"