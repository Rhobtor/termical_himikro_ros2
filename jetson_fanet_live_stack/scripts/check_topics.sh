#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "${ROOT_DIR}"

docker exec danet_ros2 bash -lc '
source /opt/ros/humble/install/setup.bash &&
cd /workspace/CPGFANet/ros2_ws &&
source install/setup.bash &&
echo "== topics ==" &&
ros2 topic list &&
echo "== rgb info ==" &&
ros2 topic info /fanet/input/rgb &&
echo "== thermal info ==" &&
ros2 topic info /fanet/input/thermal &&
echo "== outputs ==" &&
ros2 topic info /fanet/segmentation/overlay &&
ros2 topic info /fanet/person_centroid &&
ros2 topic info /fanet/person_centroids &&
ros2 topic info /fanet/person_count &&
echo "== person pose ==" &&
ros2 topic info /fanet/person_position_camera &&
ros2 topic info /fanet/person_position_robot &&
ros2 topic info /fanet/person_distance
'
