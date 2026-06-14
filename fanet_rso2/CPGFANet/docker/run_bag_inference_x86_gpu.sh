#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
WORKSPACE_ROOT=$(cd "${REPO_ROOT}/../../../" && pwd)
BAG_PATH_DEFAULT="${WORKSPACE_ROOT}/OneDrive_1_6-14-2026/rosbag2_2026_06_12-10_39_26"
OUTPUT_DIR_DEFAULT="${REPO_ROOT}/ros2_outputs/bag_inference_docker_gpu"

IMAGE_NAME=${IMAGE_NAME:-cpgfanet-x86-gpu:latest}
BAG_PATH=${BAG_PATH:-${BAG_PATH_DEFAULT}}
OUTPUT_DIR=${OUTPUT_DIR:-${OUTPUT_DIR_DEFAULT}}
MAX_PAIRS=${MAX_PAIRS:-5}
SAMPLE_STRIDE=${SAMPLE_STRIDE:-10}
RGB_TOPIC=${RGB_TOPIC:-/fanet/raw/rgb}
THERMAL_TOPIC=${THERMAL_TOPIC:-/fanet/raw/thermal}
DISPLAY_WAIT_MS=${DISPLAY_WAIT_MS:-30}
BUILD_IMAGE=${BUILD_IMAGE:-1}
STEP_THROUGH_IMAGES=${STEP_THROUGH_IMAGES:-1}
DISPLAY_SEPARATE_WINDOWS=${DISPLAY_SEPARATE_WINDOWS:-0}
ENABLE_ALIGNMENT_CHECK=${ENABLE_ALIGNMENT_CHECK:-1}
INFER_ON_ALIGNED_IMAGES=${INFER_ON_ALIGNED_IMAGES:-0}

to_ros_bool() {
  case "${1}" in
    1|true|TRUE|True|yes|YES|on|ON) echo true ;;
    0|false|FALSE|False|no|NO|off|OFF) echo false ;;
    *)
      echo "Valor booleano no valido: ${1}" >&2
      exit 2
      ;;
  esac
}

STEP_THROUGH_IMAGES_ROS=$(to_ros_bool "${STEP_THROUGH_IMAGES}")
DISPLAY_SEPARATE_WINDOWS_ROS=$(to_ros_bool "${DISPLAY_SEPARATE_WINDOWS}")
ENABLE_ALIGNMENT_CHECK_ROS=$(to_ros_bool "${ENABLE_ALIGNMENT_CHECK}")
INFER_ON_ALIGNED_IMAGES_ROS=$(to_ros_bool "${INFER_ON_ALIGNED_IMAGES}")

mkdir -p "${OUTPUT_DIR}"

if [[ "${BUILD_IMAGE}" == "1" ]]; then
  echo "[build] Construyendo imagen Docker GPU ${IMAGE_NAME}"
  docker build -f "${REPO_ROOT}/docker/x86_gpu.Dockerfile" -t "${IMAGE_NAME}" "${REPO_ROOT}"
fi

echo "[run] Lanzando inferencia GPU de rosbag con display X11"
echo "[run] Bag: ${BAG_PATH}"
echo "[run] Output: ${OUTPUT_DIR}"
echo "[run] Pares: ${MAX_PAIRS} stride=${SAMPLE_STRIDE} wait_ms=${DISPLAY_WAIT_MS} step=${STEP_THROUGH_IMAGES_ROS}"
echo "[run] Align preview: ${ENABLE_ALIGNMENT_CHECK_ROS} | aligned model input: ${INFER_ON_ALIGNED_IMAGES_ROS}"

xhost +local:root >/dev/null 2>&1 || true

docker run --rm -it \
  --gpus all \
  --env DISPLAY \
  --env QT_X11_NO_MITSHM=1 \
  --volume /tmp/.X11-unix:/tmp/.X11-unix:rw \
  --volume "${WORKSPACE_ROOT}":/workspace_host:rw \
  --name cpgfanet_bag_inference_x86_gpu \
  "${IMAGE_NAME}" \
  bash -lc "source /opt/ros/humble/setup.bash && \
    source /workspace/CPGFANet/ros2_ws/install/setup.bash && \
    python3 -m cpgfanet_inference.bag_inference_node --ros-args \
      -p repo_root:=/workspace/CPGFANet \
      -p checkpoint_path:=/workspace/CPGFANet/weights/160.pth \
      -p bag_path:=/workspace_host/${BAG_PATH#${WORKSPACE_ROOT}/} \
      -p rgb_topic:=${RGB_TOPIC} \
      -p thermal_topic:=${THERMAL_TOPIC} \
      -p output_dir:=/workspace_host/${OUTPUT_DIR#${WORKSPACE_ROOT}/} \
      -p device:=cuda \
      -p max_pairs:=${MAX_PAIRS} \
      -p sample_stride:=${SAMPLE_STRIDE} \
      -p enable_alignment_check:=${ENABLE_ALIGNMENT_CHECK_ROS} \
      -p infer_on_aligned_images:=${INFER_ON_ALIGNED_IMAGES_ROS} \
      -p display_results:=true \
      -p display_dashboard:=true \
      -p display_separate_windows:=${DISPLAY_SEPARATE_WINDOWS_ROS} \
      -p step_through_images:=${STEP_THROUGH_IMAGES_ROS} \
      -p display_wait_ms:=${DISPLAY_WAIT_MS}"