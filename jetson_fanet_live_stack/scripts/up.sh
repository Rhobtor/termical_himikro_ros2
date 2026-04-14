#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "${ROOT_DIR}"

set -a
source ./.env
set +a

./scripts/build_images.sh

docker rm -f zed_wrapper_2 hikmicro_thermal fanet_rgb_bridge fanet_pair_sync fanet_person_pose danet_ros2 >/dev/null 2>&1 || true
docker ps -aq --filter ancestor="${ZED_IMAGE}" | xargs -r docker rm -f >/dev/null 2>&1 || true

docker run -d \
	--name zed_wrapper_2 \
	--restart unless-stopped \
	--runtime nvidia \
	--network host \
	--ipc host \
	--pid host \
	--privileged \
	-e ROS_DOMAIN_ID="${ROS_DOMAIN_ID}" \
	-e RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION}" \
	-e NVIDIA_VISIBLE_DEVICES=all \
	-e NVIDIA_DRIVER_CAPABILITIES=all \
	-v /dev:/dev \
	-v /usr/local/zed/resources:/usr/local/zed/resources \
	-v /usr/local/zed/settings:/usr/local/zed/settings \
	"${ZED_IMAGE}" \
	bash -lc "source /opt/ros/humble/install/setup.bash && source /root/ros2_ws/install/setup.bash && ros2 launch zed_wrapper zed_camera.launch.py camera_model:=${ZED_CAMERA_MODEL} camera_name:=${ZED_CAMERA_NAME} node_name:=${ZED_NODE_NAME} publish_tf:=false publish_map_tf:=false publish_imu_tf:=false"

docker run -d \
	--name hikmicro_thermal \
	--restart unless-stopped \
	--runtime nvidia \
	--network host \
	--ipc host \
	--pid host \
	--privileged \
	-e ROS_DOMAIN_ID="${ROS_DOMAIN_ID}" \
	-e RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION}" \
	-e NVIDIA_VISIBLE_DEVICES=all \
	-e NVIDIA_DRIVER_CAPABILITIES=all \
	-v "${ROOT_DIR}:/workspace/deploy:ro" \
	"${HIKMICRO_IMAGE}" \
	bash -lc "source /opt/ros/humble/install/setup.bash && python3 /workspace/deploy/thermal_rtsp_publisher.py --url ${HIKMICRO_RTSP_URL} --topic ${FANET_RAW_THERMAL_TOPIC} --transport ${HIKMICRO_TRANSPORT} --width ${HIKMICRO_WIDTH} --height ${HIKMICRO_HEIGHT} --fps ${HIKMICRO_FPS}"

docker run -d \
	--name fanet_rgb_bridge \
	--restart unless-stopped \
	--runtime nvidia \
	--network host \
	--ipc host \
	--pid host \
	-e ROS_DOMAIN_ID="${ROS_DOMAIN_ID}" \
	-e RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION}" \
	-e NVIDIA_VISIBLE_DEVICES=all \
	-e NVIDIA_DRIVER_CAPABILITIES=all \
	-v "${ROOT_DIR}:/workspace/deploy:ro" \
	"${FANET_IMAGE}" \
	bash -lc "source /opt/ros/humble/install/setup.bash && python3 /workspace/deploy/rgb_topic_adapter.py --input ${ZED_RGB_TOPIC} --output ${FANET_RAW_RGB_TOPIC}"

docker run -d \
	--name fanet_pair_sync \
	--restart unless-stopped \
	--runtime nvidia \
	--network host \
	--ipc host \
	--pid host \
	-e ROS_DOMAIN_ID="${ROS_DOMAIN_ID}" \
	-e RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION}" \
	-e NVIDIA_VISIBLE_DEVICES=all \
	-e NVIDIA_DRIVER_CAPABILITIES=all \
	-v "${ROOT_DIR}:/workspace/deploy:ro" \
	"${FANET_IMAGE}" \
	bash -lc "source /opt/ros/humble/install/setup.bash && python3 /workspace/deploy/pair_sync_bridge.py --rgb-in ${FANET_RAW_RGB_TOPIC} --thermal-in ${FANET_RAW_THERMAL_TOPIC} --rgb-out ${FANET_RGB_TOPIC} --thermal-out ${FANET_THERMAL_TOPIC} --rate ${FANET_SYNC_RATE}"

docker run -d \
	--name danet_ros2 \
	--restart unless-stopped \
	--runtime nvidia \
	--network host \
	--ipc host \
	--pid host \
	-e ROS_DOMAIN_ID="${ROS_DOMAIN_ID}" \
	-e RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION}" \
	-e NVIDIA_VISIBLE_DEVICES=all \
	-e NVIDIA_DRIVER_CAPABILITIES=all \
	-v "${ROOT_DIR}:/workspace/deploy:ro" \
	-v "${FANET_OUTPUT_DIR}:/workspace/CPGFANet/ros2_outputs" \
	"${FANET_IMAGE}" \
	bash -lc "source /opt/ros/humble/install/setup.bash && cd /workspace/CPGFANet/ros2_ws && source install/setup.bash && ros2 run cpgfanet_inference topic_inference --ros-args --params-file ${FANET_PARAMS_FILE} -p rgb_topic:=${FANET_RGB_TOPIC} -p thermal_topic:=${FANET_THERMAL_TOPIC}"

docker run -d \
	--name fanet_person_pose \
	--restart unless-stopped \
	--runtime nvidia \
	--network host \
	--ipc host \
	--pid host \
	-e ROS_DOMAIN_ID="${ROS_DOMAIN_ID}" \
	-e RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION}" \
	-e NVIDIA_VISIBLE_DEVICES=all \
	-e NVIDIA_DRIVER_CAPABILITIES=all \
	-v "${ROOT_DIR}:/workspace/deploy:ro" \
	"${FANET_IMAGE}" \
	bash -lc "source /opt/ros/humble/install/setup.bash && python3 /workspace/deploy/person_position_from_depth.py --centroid-topic ${FANET_PERSON_CENTROID_TOPIC} --centroids-topic ${FANET_PERSON_CENTROIDS_TOPIC} --overlay-topic ${FANET_OVERLAY_TOPIC} --depth-topic ${ZED_DEPTH_TOPIC} --camera-info-topic ${ZED_DEPTH_CAMERA_INFO_TOPIC} --camera-position-topic ${FANET_PERSON_POSITION_CAMERA_TOPIC} --robot-position-topic ${FANET_PERSON_POSITION_ROBOT_TOPIC} --distance-topic ${FANET_PERSON_DISTANCE_TOPIC}"

echo "Stack levantado."
echo "Usa ./scripts/check_topics.sh para validar los topics."
echo "Usa ./scripts/monitor_fanet.sh para ver CPU, memoria, GPU e inferencia."
