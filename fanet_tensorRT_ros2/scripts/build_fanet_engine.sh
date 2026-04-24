#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Uso: $0 <input.onnx> <output.engine> [workspace_mb]" >&2
  exit 1
fi

INPUT_ONNX=$1
OUTPUT_ENGINE=$2
WORKSPACE_MB=${3:-4096}

TRTEXEC_BIN=${TRTEXEC_BIN:-$(command -v trtexec || true)}
if [[ -z "${TRTEXEC_BIN}" && -x /usr/src/tensorrt/bin/trtexec ]]; then
  TRTEXEC_BIN=/usr/src/tensorrt/bin/trtexec
fi

if [[ -z "${TRTEXEC_BIN}" ]]; then
  echo "trtexec no esta disponible en este entorno." >&2
  echo "Instala TensorRT CLI en la Jetson o usa un contenedor que ya la incluya." >&2
  exit 1
fi

mkdir -p "$(dirname "${OUTPUT_ENGINE}")"

"${TRTEXEC_BIN}" \
  --onnx="${INPUT_ONNX}" \
  --saveEngine="${OUTPUT_ENGINE}" \
  --fp16 \
  --workspace="${WORKSPACE_MB}" \
  --verbose

echo "Engine TensorRT generado en: ${OUTPUT_ENGINE}"
