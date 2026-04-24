#!/usr/bin/env bash
set -euo pipefail

TRT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "${TRT_ROOT}/scripts/config.sh"

if [[ ! -d "${LIVE_STACK_ROOT}" ]]; then
  echo "No existe LIVE_STACK_ROOT: ${LIVE_STACK_ROOT}" >&2
  exit 1
fi

if [[ ! -f "${FANET_ENGINE_PATH}" ]]; then
  echo "Engine TensorRT no encontrado: ${FANET_ENGINE_PATH}" >&2
  echo "Ejecuta antes ./scripts/build_all_artifacts.sh o al menos ./scripts/build_engine_docker.sh" >&2
  exit 1
fi

if ! docker image inspect "${TRT_IMAGE_NAME}" >/dev/null 2>&1; then
  echo "Imagen TensorRT no encontrada: ${TRT_IMAGE_NAME}" >&2
  echo "Construyendo imagen TensorRT..."
  "${TRT_ROOT}/scripts/build_image.sh"
fi

source "${LIVE_STACK_ROOT}/scripts/config.sh"

mkdir -p "${FANET_HOST_WEIGHTS_DIR}"
if [[ ! -f "${FANET_HOST_CHECKPOINT_PATH}" ]]; then
  echo "Falta el checkpoint de FANet: ${FANET_HOST_CHECKPOINT_PATH}" >&2
  exit 1
fi

cd "${LIVE_STACK_ROOT}"
./scripts/build_images.sh

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
  -v "${LIVE_STACK_ROOT}:/workspace/deploy:ro" \
  "${HIKMICRO_IMAGE}" \
  bash -lc "source /opt/ros/humble/install/setup.bash && source /workspace/hikmicro_ws/install/setup.bash && ros2 run hikmicro_thermal_camera ${HIKMICRO_NODE_EXECUTABLE} --ros-args -p url:=${HIKMICRO_RTSP_URL} -p topic_name:=${FANET_RAW_THERMAL_TOPIC} -p transport:=${HIKMICRO_TRANSPORT} -p width:=${HIKMICRO_WIDTH} -p height:=${HIKMICRO_HEIGHT} -p fps:=${HIKMICRO_FPS} -p reconnect_delay_ms:=${HIKMICRO_RECONNECT_DELAY_MS} -p ffmpeg_log_level:=${HIKMICRO_FFMPEG_LOG_LEVEL} -p scale_output:=${HIKMICRO_SCALE_OUTPUT}"

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
  -v "${LIVE_STACK_ROOT}:/workspace/deploy:ro" \
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
  -v "${LIVE_STACK_ROOT}:/workspace/deploy:ro" \
  "${FANET_IMAGE}" \
  bash -lc "source /opt/ros/humble/install/setup.bash && python3 /workspace/deploy/pair_sync_bridge.py --rgb-in ${FANET_RAW_RGB_TOPIC} --thermal-in ${FANET_RAW_THERMAL_TOPIC} --rgb-out ${FANET_RGB_TOPIC} --thermal-out ${FANET_THERMAL_TOPIC} --rate ${FANET_SYNC_RATE} --max-age-s ${FANET_SYNC_MAX_AGE_S} --max-delta-s ${FANET_SYNC_MAX_DELTA_S}"

"${TRT_ROOT}/scripts/run_trt_topic_inference_docker.sh"

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
  -v "${LIVE_STACK_ROOT}:/workspace/deploy:ro" \
  "${FANET_IMAGE}" \
  bash -lc "source /opt/ros/humble/install/setup.bash && python3 /workspace/deploy/person_position_from_depth.py --centroid-topic ${FANET_PERSON_CENTROID_TOPIC} --centroids-topic ${FANET_PERSON_CENTROIDS_TOPIC} --depth-topic ${ZED_DEPTH_TOPIC} --camera-info-topic ${ZED_DEPTH_CAMERA_INFO_TOPIC} --camera-position-topic ${FANET_PERSON_POSITION_CAMERA_TOPIC} --camera-positions-topic ${FANET_PERSON_POSITIONS_CAMERA_TOPIC} --robot-position-topic ${FANET_PERSON_POSITION_ROBOT_TOPIC} --robot-positions-topic ${FANET_PERSON_POSITIONS_ROBOT_TOPIC} --distance-topic ${FANET_PERSON_DISTANCE_TOPIC} --distances-topic ${FANET_PERSON_DISTANCES_TOPIC} --model-width ${FANET_MODEL_WIDTH} --model-height ${FANET_MODEL_HEIGHT}"

docker run -d \
  --name fanet_gui_topics \
  --restart unless-stopped \
  --runtime nvidia \
  --network host \
  --ipc host \
  --pid host \
  -e ROS_DOMAIN_ID="${ROS_DOMAIN_ID}" \
  -e RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION}" \
  -e NVIDIA_VISIBLE_DEVICES=all \
  -e NVIDIA_DRIVER_CAPABILITIES=all \
  -v "${TRT_ROOT}:/workspace/fanet_tensorRT_ros2" \
  "${TRT_IMAGE_NAME}" \
  bash -lc "set -e && source /opt/ros/humble/install/setup.bash && cd /workspace/fanet_tensorRT_ros2/ros2_ws && colcon build --packages-select cpgfanet_trt_gui --merge-install && source install/setup.bash && ros2 run cpgfanet_trt_gui rgb_person_annotator --ros-args -p rgb_topic:=${FANET_RGB_TOPIC} -p centroid_topic:=${FANET_PERSON_CENTROID_TOPIC} -p centroids_topic:=${FANET_PERSON_CENTROIDS_TOPIC} -p robot_position_topic:=${FANET_PERSON_POSITION_ROBOT_TOPIC} -p distance_topic:=${FANET_PERSON_DISTANCE_TOPIC} -p rgb_output_topic:=${FANET_GUI_RGB_TOPIC} -p model_width:=${FANET_MODEL_WIDTH} -p model_height:=${FANET_MODEL_HEIGHT}"

echo "Stack TensorRT levantado."
echo "Logs TensorRT: docker logs -f ${TRT_NODE_CONTAINER_NAME}"
echo "Parada completa: ${TRT_ROOT}/scripts/down_trt_stack.sh"
