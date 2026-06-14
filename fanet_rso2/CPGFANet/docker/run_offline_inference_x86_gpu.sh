#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
WORKSPACE_ROOT=$(cd "${REPO_ROOT}/../../../" && pwd)
RGB_DIR_DEFAULT="${WORKSPACE_ROOT}/rosbag_extract_all/rgb"
THERMAL_DIR_DEFAULT="${WORKSPACE_ROOT}/rosbag_extract_all/thermal_raw"
OUTPUT_DIR_DEFAULT="${WORKSPACE_ROOT}/offline_curated_outputs"

IMAGE_NAME=${IMAGE_NAME:-cpgfanet-x86-gpu:latest}
RGB_DIR=${RGB_DIR:-${RGB_DIR_DEFAULT}}
THERMAL_DIR=${THERMAL_DIR:-${THERMAL_DIR_DEFAULT}}
OUTPUT_DIR=${OUTPUT_DIR:-${OUTPUT_DIR_DEFAULT}}
MAX_IMAGES=${MAX_IMAGES:-0}
DISPLAY_WAIT_MS=${DISPLAY_WAIT_MS:-30}
BUILD_IMAGE=${BUILD_IMAGE:-0}
INPUT_WIDTH=${INPUT_WIDTH:-640}
INPUT_HEIGHT=${INPUT_HEIGHT:-360}
SAVE_OUTPUTS=${SAVE_OUTPUTS:-1}
DISPLAY_RESULTS=${DISPLAY_RESULTS:-1}
STEP_THROUGH_IMAGES=${STEP_THROUGH_IMAGES:-1}
DISPLAY_DASHBOARD=${DISPLAY_DASHBOARD:-1}
DISPLAY_SEPARATE_WINDOWS=${DISPLAY_SEPARATE_WINDOWS:-0}

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

SAVE_OUTPUTS_ROS=$(to_ros_bool "${SAVE_OUTPUTS}")
DISPLAY_RESULTS_ROS=$(to_ros_bool "${DISPLAY_RESULTS}")
STEP_THROUGH_IMAGES_ROS=$(to_ros_bool "${STEP_THROUGH_IMAGES}")
DISPLAY_DASHBOARD_ROS=$(to_ros_bool "${DISPLAY_DASHBOARD}")
DISPLAY_SEPARATE_WINDOWS_ROS=$(to_ros_bool "${DISPLAY_SEPARATE_WINDOWS}")

mkdir -p "${OUTPUT_DIR}"

if [[ "${BUILD_IMAGE}" == "1" ]]; then
  echo "[build] Construyendo imagen Docker GPU ${IMAGE_NAME}"
  docker build -f "${REPO_ROOT}/docker/x86_gpu.Dockerfile" -t "${IMAGE_NAME}" "${REPO_ROOT}"
fi

echo "[run] Lanzando inferencia offline GPU con display X11"
echo "[run] RGB: ${RGB_DIR}"
echo "[run] Thermal: ${THERMAL_DIR}"
echo "[run] Output: ${OUTPUT_DIR}"
echo "[run] Max images: ${MAX_IMAGES} wait_ms=${DISPLAY_WAIT_MS} size=${INPUT_WIDTH}x${INPUT_HEIGHT}"
echo "[run] Dashboard: ${DISPLAY_DASHBOARD_ROS} | step: ${STEP_THROUGH_IMAGES_ROS} | separate: ${DISPLAY_SEPARATE_WINDOWS_ROS}"

xhost +local:root >/dev/null 2>&1 || true

docker run --rm -it \
  --gpus all \
  --env DISPLAY \
  --env QT_X11_NO_MITSHM=1 \
  --volume /tmp/.X11-unix:/tmp/.X11-unix:rw \
  --volume "${WORKSPACE_ROOT}":/workspace_host:rw \
  --name cpgfanet_offline_inference_x86_gpu \
  "${IMAGE_NAME}" \
  bash -lc "source /opt/ros/humble/setup.bash && \
    source /workspace/CPGFANet/ros2_ws/install/setup.bash && \
    python3 -m cpgfanet_inference.offline_inference_node --ros-args \
      -p repo_root:=/workspace/CPGFANet \
      -p checkpoint_path:=/workspace/CPGFANet/weights/160.pth \
      -p model_module:=model.CrissCrossAttention_dual_2_sinINF \
      -p model_class:=FEANet \
      -p num_classes:=12 \
      -p rgb_image_dir:=/workspace_host/${RGB_DIR#${WORKSPACE_ROOT}/} \
      -p thermal_image_dir:=/workspace_host/${THERMAL_DIR#${WORKSPACE_ROOT}/} \
      -p output_dir:=/workspace_host/${OUTPUT_DIR#${WORKSPACE_ROOT}/} \
      -p device:=cuda \
      -p input_width:=${INPUT_WIDTH} \
      -p input_height:=${INPUT_HEIGHT} \
      -p max_images:=${MAX_IMAGES} \
      -p save_outputs:=${SAVE_OUTPUTS_ROS} \
      -p display_results:=${DISPLAY_RESULTS_ROS} \
      -p step_through_images:=${STEP_THROUGH_IMAGES_ROS} \
      -p display_dashboard:=${DISPLAY_DASHBOARD_ROS} \
      -p display_separate_windows:=${DISPLAY_SEPARATE_WINDOWS_ROS} \
      -p display_wait_ms:=${DISPLAY_WAIT_MS} \
      -p run_once:=false \
      -p loop_dataset:=false"