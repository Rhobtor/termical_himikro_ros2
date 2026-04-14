#!/usr/bin/env bash
set -euo pipefail

REPO_SRC=/home/isa/Documents/Luis/himikro_termical/termical_himikro_ros2
BENCH_WS=/home/isa/Documents/Luis/hikmicro_bench_ws

if [[ ! -d "$REPO_SRC/src" ]]; then
  echo "No existe el repo Hikmicro esperado en: $REPO_SRC" >&2
  exit 1
fi

mkdir -p "$BENCH_WS/src"
rm -rf "$BENCH_WS/src/hikmicro_thermal_camera"
cp -a "$REPO_SRC" "$BENCH_WS/src/hikmicro_thermal_camera"

docker run --rm \
  --user "$(id -u):$(id -g)" \
  --runtime nvidia \
  --network host \
  -v "$BENCH_WS:/workspace/hikmicro_ws" \
  cpgfanet_ros2_jetson:humble \
  bash -lc 'set -e; source /opt/ros/humble/install/setup.bash; cd /workspace/hikmicro_ws; colcon build --packages-select hikmicro_thermal_camera --cmake-clean-cache'

echo "Workspace Hikmicro sincronizado y recompilado en: $BENCH_WS"
