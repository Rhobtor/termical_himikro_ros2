#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

export TRT_IMAGE_NAME=fanet_trt_builder:jetson
export TRT_BASE_IMAGE=dustynv/ros:humble-pytorch-l4t-r35.3.1
export TRT_NODE_CONTAINER_NAME=fanet_trt_topic_inference

export LIVE_STACK_ROOT=/home/isa/Documents/Luis/himikro_termical/termical_himikro_ros2/jetson_fanet_live_stack

export FANET_PYTORCH_REPO=/home/isa/Documents/Luis/himikro_termical/termical_himikro_ros2/fanet_rso2/CPGFANet
export FANET_HOST_WEIGHTS_DIR=/home/isa/Documents/Luis/fanet_rso2
export FANET_CHECKPOINT_NAME=160.pth
export FANET_HOST_CHECKPOINT_PATH=${FANET_HOST_WEIGHTS_DIR}/${FANET_CHECKPOINT_NAME}

export FANET_MODEL_MODULE=model.CrissCrossAttention_dual_2_sinINF
export FANET_MODEL_CLASS=FEANet
export FANET_NUM_CLASSES=12
export FANET_INPUT_WIDTH=448
export FANET_INPUT_HEIGHT=352

export ARTIFACTS_DIR=${ROOT_DIR}/artifacts
export FANET_ONNX_PATH=${ARTIFACTS_DIR}/fanet_${FANET_INPUT_WIDTH}x${FANET_INPUT_HEIGHT}.onnx
export FANET_ENGINE_PATH=${ARTIFACTS_DIR}/fanet_${FANET_INPUT_WIDTH}x${FANET_INPUT_HEIGHT}_fp16.engine
export TRT_WORKSPACE_MB=4096
export TRT_PARAMS_FILE=${ROOT_DIR}/configs/fanet_trt.params.yaml

