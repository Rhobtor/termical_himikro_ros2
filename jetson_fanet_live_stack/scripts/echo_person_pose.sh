#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "${ROOT_DIR}"

source "${ROOT_DIR}/scripts/config.sh"

MODE=${1:-once}

case "${MODE}" in
	once)
		docker exec \
		  -e ROS_DOMAIN_ID="${ROS_DOMAIN_ID}" \
		  -e RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION}" \
		  fanet_person_pose bash -lc '
			source /opt/ros/humble/install/setup.bash &&
			echo "== /fanet/person_positions_robot ==" &&
			timeout 8 ros2 topic echo --once /fanet/person_positions_robot &&
			echo "== /fanet/person_distances ==" &&
			timeout 8 ros2 topic echo --once /fanet/person_distances
		  '
		;;
	watch)
		echo "Abre otra terminal si quieres ver ambos a la vez."
		echo "Terminal 1: docker exec -e ROS_DOMAIN_ID=${ROS_DOMAIN_ID} -e RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION} fanet_person_pose bash -lc 'source /opt/ros/humble/install/setup.bash && ros2 topic echo /fanet/person_positions_robot'"
		echo "Terminal 2: docker exec -e ROS_DOMAIN_ID=${ROS_DOMAIN_ID} -e RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION} fanet_person_pose bash -lc 'source /opt/ros/humble/install/setup.bash && ros2 topic echo /fanet/person_distances'"
		;;
	*)
		echo "Uso: $0 [once|watch]" >&2
		exit 1
		;;
esac