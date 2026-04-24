#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "${ROOT_DIR}/scripts/config.sh"
source "${LIVE_STACK_ROOT}/scripts/config.sh"

docker exec \
  -e ROS_DOMAIN_ID="${ROS_DOMAIN_ID}" \
  -e RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION}" \
  "${TRT_NODE_CONTAINER_NAME}" bash -lc '
source /opt/ros/humble/install/setup.bash &&
ros2 daemon stop >/dev/null 2>&1 || true &&
echo "== topics ==" &&
ros2 topic list &&
echo "== model inputs ==" &&
ros2 topic info /fanet/input/rgb &&
ros2 topic info /fanet/input/thermal &&
echo "== outputs ==" &&
ros2 topic info /fanet/person_centroid &&
ros2 topic info /fanet/person_centroids &&
ros2 topic info /fanet/person_count &&
ros2 topic info /fanet/person_distance &&
ros2 topic info /fanet/person_distances &&
ros2 topic info /fanet/person_position_robot &&
ros2 topic info /fanet/person_positions_robot &&
ros2 topic info /fanet/gui/rgb_annotated &&
ros2 topic info /fanet/gui/thermal_annotated
'
