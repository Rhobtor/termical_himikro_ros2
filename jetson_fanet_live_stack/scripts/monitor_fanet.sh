#!/usr/bin/env bash
set -euo pipefail

MODE=${1:-stats}
ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

topic_probe() {
  local duration=${1}
  shift
  docker exec danet_ros2 bash -lc "source /opt/ros/humble/install/setup.bash && cd /workspace/CPGFANet/ros2_ws && source install/setup.bash && python3 /workspace/deploy/topic_fps_probe.py --duration ${duration} $*"
}

host_snapshot() {
  echo "== host tegrastats =="
  timeout 3s tegrastats --interval 1000 2>/dev/null | tail -n 1 || true
  echo
  echo "== host memoria =="
  free -h
  echo
  echo "== host carga =="
  uptime
}

case "${MODE}" in
  stats)
    docker stats danet_ros2 fanet_pair_sync fanet_rgb_bridge hikmicro_thermal zed_wrapper_2
    ;;
  stats-once)
    docker stats --no-stream danet_ros2 fanet_pair_sync fanet_rgb_bridge hikmicro_thermal zed_wrapper_2
    ;;
  perf)
    docker logs -f danet_ros2 2>&1 | grep -E 'Rendimiento topic FANet|Modelo de inferencia|cuda_mem|gpu_load|processed='
    ;;
  jetson)
    tegrastats --interval 1000
    ;;
  jetson-once)
    host_snapshot
    ;;
  fps-capture)
    topic_probe 6 "--topic /zed/zed_node/left/image_rect_color --topic /fanet/raw/thermal"
    ;;
  fps-model)
    topic_probe 6 "--topic /fanet/input/rgb --topic /fanet/input/thermal"
    ;;
  fps-output)
    topic_probe 6 "--topic /fanet/segmentation/overlay"
    ;;
  topics)
    echo "== fps captura =="
    topic_probe 6 "--topic /zed/zed_node/left/image_rect_color --topic /fanet/raw/thermal"
    echo
    echo "== fps entrada al modelo =="
    topic_probe 6 "--topic /fanet/input/rgb --topic /fanet/input/thermal"
    echo
    echo "== fps salida modelo =="
    topic_probe 6 "--topic /fanet/segmentation/overlay"
    ;;
  snapshot)
    echo "== docker =="
    docker stats --no-stream danet_ros2 fanet_pair_sync fanet_rgb_bridge hikmicro_thermal zed_wrapper_2
    echo
    host_snapshot
    echo
    echo "== fps entrada al modelo =="
    topic_probe 6 "--topic /fanet/input/rgb --topic /fanet/input/thermal"
    ;;
  *)
    echo "Uso: $0 [stats|stats-once|perf|jetson|jetson-once|fps-capture|fps-model|fps-output|topics|snapshot]"
    exit 1
    ;;
esac
