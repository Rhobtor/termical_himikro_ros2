#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "${ROOT_DIR}"

source "${ROOT_DIR}/scripts/config.sh"

docker exec \
	-e ROS_DOMAIN_ID="${ROS_DOMAIN_ID}" \
	-e RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION}" \
	danet_ros2 bash -lc '
source /opt/ros/humble/install/setup.bash &&
cd /workspace/CPGFANet/ros2_ws &&
source install/setup.bash &&
ros2 daemon stop >/dev/null 2>&1 || true &&
echo "== topics ==" &&
ros2 topic list &&
echo "== rgb info ==" &&
ros2 topic info /fanet/input/rgb &&
echo "== thermal info ==" &&
ros2 topic info /fanet/input/thermal &&
ros2 topic info /fanet/raw/thermal/compressed &&
echo "== outputs ==" &&
ros2 topic info /fanet/segmentation/overlay &&
ros2 topic info /fanet/person_centroid &&
ros2 topic info /fanet/person_centroids &&
ros2 topic info /fanet/person_count &&
echo "== person pose ==" &&
ros2 topic info /fanet/person_position_camera &&
ros2 topic info /fanet/person_positions_camera &&
ros2 topic info /fanet/person_position_robot &&
ros2 topic info /fanet/person_distance &&
ros2 topic info /fanet/person_positions_robot &&
ros2 topic info /fanet/person_distances &&
echo "== gui topics ==" &&
ros2 topic info /fanet/gui/rgb_annotated &&
ros2 topic info /fanet/gui/thermal_annotated &&
ros2 topic info /fanet/gui/rgb_annotated/compressed &&
ros2 topic info /fanet/gui/thermal_annotated/compressed
'
