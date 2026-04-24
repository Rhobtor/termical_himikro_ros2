#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "${ROOT_DIR}/scripts/config.sh"

mkdir -p "${ARTIFACTS_DIR}"

if [[ ! -f "${FANET_HOST_CHECKPOINT_PATH}" ]]; then
  echo "Checkpoint no encontrado: ${FANET_HOST_CHECKPOINT_PATH}" >&2
  exit 1
fi

docker run --rm \
  --runtime nvidia \
  --network host \
  -e NVIDIA_VISIBLE_DEVICES=all \
  -e NVIDIA_DRIVER_CAPABILITIES=all \
  -v "${ROOT_DIR}:/workspace/fanet_tensorRT_ros2" \
  -v "${FANET_PYTORCH_REPO}:/workspace/CPGFANet:ro" \
  -v "${FANET_HOST_WEIGHTS_DIR}:/workspace/weights:ro" \
  "${TRT_IMAGE_NAME}" \
  bash -lc "python3 /workspace/fanet_tensorRT_ros2/scripts/export_fanet_onnx.py --repo-root /workspace/CPGFANet --checkpoint /workspace/weights/${FANET_CHECKPOINT_NAME} --output /workspace/fanet_tensorRT_ros2/artifacts/$(basename "${FANET_ONNX_PATH}") --model-module ${FANET_MODEL_MODULE} --model-class ${FANET_MODEL_CLASS} --num-classes ${FANET_NUM_CLASSES} --input-width ${FANET_INPUT_WIDTH} --input-height ${FANET_INPUT_HEIGHT} --device cuda"

echo "ONNX generado en: ${FANET_ONNX_PATH}"
