#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source "${ROOT_DIR}/scripts/config.sh"

docker build \
  --build-arg BASE_IMAGE="${TRT_BASE_IMAGE}" \
  -t "${TRT_IMAGE_NAME}" \
  -f "${ROOT_DIR}/Dockerfile" \
  "${ROOT_DIR}"

echo "Imagen TensorRT lista: ${TRT_IMAGE_NAME}"
