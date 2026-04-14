#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
HIK_WS=/home/isa/Documents/Luis/hikmicro_bench_ws
IMAGE=${IMAGE:-hikmicro_thermal_ros2:jetson}
DISPLAY_VALUE=${DISPLAY:-:0}
XAUTHORITY_VALUE=${XAUTHORITY:-$HOME/.Xauthority}

docker rm -f hikmicro_bench_shell >/dev/null 2>&1 || true

DOCKER_ARGS=(
  --rm
  -it
  --name hikmicro_bench_shell
  --runtime nvidia
  --network host
  --ipc host
  --pid host
  --privileged
  -e ROS_DOMAIN_ID=30
  -e RMW_IMPLEMENTATION=rmw_fastrtps_cpp
  -e NVIDIA_VISIBLE_DEVICES=all
  -e NVIDIA_DRIVER_CAPABILITIES=all
  -e DISPLAY=${DISPLAY_VALUE}
  -v /home/isa/Documents/Luis/hikmicro_bench_ws:/workspace/hikmicro_ws
  -v /home/isa/Documents/Luis/jetson_fanet_live_stack:/workspace/deploy:ro
)

if [[ -d /tmp/.X11-unix ]]; then
  DOCKER_ARGS+=( -v /tmp/.X11-unix:/tmp/.X11-unix:rw )
fi

if [[ -f "${XAUTHORITY_VALUE}" ]]; then
  DOCKER_ARGS+=( -e XAUTHORITY=${XAUTHORITY_VALUE} -v "${XAUTHORITY_VALUE}:${XAUTHORITY_VALUE}:ro" )
fi

docker run "${DOCKER_ARGS[@]}" \
  "${IMAGE}" \
  bash -lc 'source /opt/ros/humble/install/setup.bash && cd /workspace/hikmicro_ws && source install/setup.bash && bash'
