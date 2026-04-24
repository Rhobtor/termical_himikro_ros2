#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

cd "${ROOT_DIR}"
./scripts/build_image.sh
./scripts/export_onnx_docker.sh
./scripts/build_engine_docker.sh

echo "Artefactos TensorRT listos en ${ROOT_DIR}/artifacts"
