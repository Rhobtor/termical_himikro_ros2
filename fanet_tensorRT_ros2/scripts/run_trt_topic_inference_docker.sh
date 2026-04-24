#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "${ROOT_DIR}/scripts/config.sh"

PARAMS_FILE=${PARAMS_FILE:-/workspace/fanet_tensorRT_ros2/configs/fanet_trt.params.yaml}
ROS_DOMAIN_ID_VALUE=${ROS_DOMAIN_ID:-0}
RMW_IMPLEMENTATION_VALUE=${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}
CONTAINER_NAME=${CONTAINER_NAME:-fanet_trt_topic_inference}

if [[ ! -f "${FANET_ENGINE_PATH}" ]]; then
  echo "Engine no encontrado: ${FANET_ENGINE_PATH}" >&2
  echo "Ejecuta antes ./scripts/build_engine_docker.sh" >&2
  exit 1
fi

docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

docker run -d \
  --name "${CONTAINER_NAME}" \
  --restart unless-stopped \
  --runtime nvidia \
  --network host \
  --ipc host \
  --pid host \
  -e ROS_DOMAIN_ID="${ROS_DOMAIN_ID_VALUE}" \
  -e RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION_VALUE}" \
  -e NVIDIA_VISIBLE_DEVICES=all \
  -e NVIDIA_DRIVER_CAPABILITIES=all \
  -v "${ROOT_DIR}:/workspace/fanet_tensorRT_ros2" \
  "${TRT_IMAGE_NAME}" \
  bash -lc "source /opt/ros/humble/install/setup.bash && export PYTHONPATH=/workspace/fanet_tensorRT_ros2/ros2_ws/src/cpgfanet_trt_inference:\${PYTHONPATH:-} && python3 -m cpgfanet_trt_inference.topic_inference_trt_node --ros-args --params-file ${PARAMS_FILE}"

echo "Nodo TensorRT lanzado en contenedor ${CONTAINER_NAME}"
echo "Logs: docker logs -f ${CONTAINER_NAME}"
echo "Parada: docker rm -f ${CONTAINER_NAME}"