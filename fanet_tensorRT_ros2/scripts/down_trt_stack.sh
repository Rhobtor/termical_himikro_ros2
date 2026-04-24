#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "${ROOT_DIR}/scripts/config.sh"

docker rm -f \
  "${TRT_NODE_CONTAINER_NAME}" \
  zed_wrapper_2 \
  hikmicro_thermal \
  fanet_rgb_bridge \
  fanet_pair_sync \
  fanet_person_pose \
  fanet_gui_topics \
  danet_ros2 \
  >/dev/null 2>&1 || true

echo "Stack TensorRT detenido."
