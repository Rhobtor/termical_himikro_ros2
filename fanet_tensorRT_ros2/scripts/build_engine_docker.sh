#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "${ROOT_DIR}/scripts/config.sh"

mkdir -p "${ARTIFACTS_DIR}"

if [[ ! -f "${FANET_ONNX_PATH}" ]]; then
  echo "ONNX no encontrado: ${FANET_ONNX_PATH}" >&2
  echo "Ejecuta antes ./scripts/export_onnx_docker.sh" >&2
  exit 1
fi

docker run --rm \
  --runtime nvidia \
  --network host \
  -e NVIDIA_VISIBLE_DEVICES=all \
  -e NVIDIA_DRIVER_CAPABILITIES=all \
  -v "${ROOT_DIR}:/workspace/fanet_tensorRT_ros2" \
  "${TRT_IMAGE_NAME}" \
  bash -lc "cd /workspace/fanet_tensorRT_ros2 && ./scripts/build_fanet_engine.sh /workspace/fanet_tensorRT_ros2/artifacts/$(basename "${FANET_ONNX_PATH}") /workspace/fanet_tensorRT_ros2/artifacts/$(basename "${FANET_ENGINE_PATH}") ${TRT_WORKSPACE_MB}"

echo "Engine TensorRT generado en: ${FANET_ENGINE_PATH}"