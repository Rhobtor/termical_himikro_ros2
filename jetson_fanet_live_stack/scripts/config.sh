#!/usr/bin/env bash
set -euo pipefail

STACK_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

export ROS_DOMAIN_ID=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp

export L4T_VERSION=l4t-r35.3.1
export L4T_MAJOR=35
export L4T_MINOR=3
export JETSON_ROS_BASE_IMAGE=dustynv/ros:humble-ros-base-l4t-r35.3.1
export FANET_BASE_IMAGE=dustynv/ros:humble-pytorch-l4t-r35.3.1

export ZED_SDK_MAJOR=4
export ZED_SDK_MINOR=1
export ZED_SDK_PATCH=4
export ZED_IMAGE=zed_wrapper_2:latest
export ZED_BUILD=0
export ZED_CAMERA_MODEL=zed2i
export ZED_CAMERA_NAME=zed
export ZED_NODE_NAME=zed_node
export ZED_RGB_TOPIC=/zed/zed_node/left/image_rect_color
export ZED_DEPTH_TOPIC=/zed/zed_node/depth/depth_registered
export ZED_DEPTH_CAMERA_INFO_TOPIC=/zed/zed_node/depth/camera_info

export HIKMICRO_IMAGE=hikmicro_thermal_ros2:jetson
export HIKMICRO_BUILD=0
export HIKMICRO_NODE_EXECUTABLE=termical_camera_ffmpeg_pipe
export HIKMICRO_RTSP_URL=rtsp://admin:laentiec27@192.168.2.64:554/Streaming/Channels/101
export HIKMICRO_TRANSPORT=tcp
export HIKMICRO_WIDTH=640
export HIKMICRO_HEIGHT=512
export HIKMICRO_FPS=25.0
export HIKMICRO_JPEG_QUALITY=60
export HIKMICRO_RECONNECT_DELAY_MS=300
export HIKMICRO_FFMPEG_LOG_LEVEL=error
export HIKMICRO_SCALE_OUTPUT=false

export FANET_IMAGE=cpgfanet_ros2_jetson:humble
export FANET_BUILD=0
export FANET_PARAMS_FILE=/workspace/deploy/fanet_tuned.params.yaml
export FANET_HOST_WEIGHTS_DIR=/home/isa/Documents/Luis/fanet_rso2
export FANET_CHECKPOINT_NAME=160.pth
export FANET_HOST_CHECKPOINT_PATH=${FANET_HOST_WEIGHTS_DIR}/${FANET_CHECKPOINT_NAME}
export FANET_CONTAINER_WEIGHTS_DIR=/workspace/CPGFANet/weights
export FANET_CONTAINER_CHECKPOINT_PATH=${FANET_CONTAINER_WEIGHTS_DIR}/${FANET_CHECKPOINT_NAME}
export FANET_RAW_RGB_TOPIC=/fanet/raw/rgb
export FANET_RAW_THERMAL_TOPIC=/fanet/raw/thermal
export FANET_RAW_THERMAL_COMPRESSED_TOPIC=/fanet/raw/thermal/compressed
export FANET_RGB_TOPIC=/fanet/input/rgb
export FANET_THERMAL_TOPIC=/fanet/input/thermal
export FANET_OVERLAY_TOPIC=/fanet/segmentation/overlay
export FANET_PERSON_CENTROID_TOPIC=/fanet/person_centroid
export FANET_PERSON_CENTROIDS_TOPIC=/fanet/person_centroids
export FANET_PERSON_COUNT_TOPIC=/fanet/person_count
export FANET_PERSON_POSITION_CAMERA_TOPIC=/fanet/person_position_camera
export FANET_PERSON_POSITIONS_CAMERA_TOPIC=/fanet/person_positions_camera
export FANET_PERSON_POSITION_ROBOT_TOPIC=/fanet/person_position_robot
export FANET_PERSON_POSITIONS_ROBOT_TOPIC=/fanet/person_positions_robot
export FANET_PERSON_DISTANCE_TOPIC=/fanet/person_distance
export FANET_PERSON_DISTANCES_TOPIC=/fanet/person_distances
export FANET_GUI_RGB_TOPIC=/fanet/gui/rgb_annotated
export FANET_GUI_THERMAL_TOPIC=/fanet/gui/thermal_annotated
export FANET_GUI_RGB_COMPRESSED_TOPIC=/fanet/gui/rgb_annotated/compressed
export FANET_GUI_THERMAL_COMPRESSED_TOPIC=/fanet/gui/thermal_annotated/compressed
export FANET_GUI_JPEG_QUALITY=70
export FANET_OUTPUT_DIR=${STACK_ROOT}/../fanet_rso2/CPGFANet/ros2_outputs
export FANET_SYNC_RATE=6.0
export FANET_SYNC_MAX_AGE_S=0.20
export FANET_SYNC_MAX_DELTA_S=0.08