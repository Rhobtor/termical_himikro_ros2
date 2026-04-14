#!/usr/bin/env bash
set -euo pipefail

DURATION=${1:-15}
ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPORT_DIR="${ROOT_DIR}/logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_FILE="${REPORT_DIR}/runtime_report_${TIMESTAMP}.log"
TEGRA_FILE="${REPORT_DIR}/tegrastats_${TIMESTAMP}.log"
PERF_FILE="${REPORT_DIR}/model_perf_${TIMESTAMP}.log"

mkdir -p "${REPORT_DIR}"

if ! docker ps --format '{{.Names}}' | grep -q '^danet_ros2$'; then
  echo "No existe el contenedor danet_ros2. Lanza antes ./scripts/up.sh" >&2
  exit 1
fi

{
  echo "# Runtime report"
  echo "timestamp=${TIMESTAMP}"
  echo "duration_s=${DURATION}"
  echo "host=$(hostname)"
  echo
  echo "## Nota"
  echo "Idealmente ejecuta esta captura mientras haya una persona visible delante de la camara."
  echo
  echo "## Docker containers"
  docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
  echo
  echo "## Docker stats snapshot"
  docker stats --no-stream danet_ros2 fanet_pair_sync fanet_rgb_bridge hikmicro_thermal zed_wrapper_2 || true
  echo
  echo "## Host memory"
  free -h
  echo
  echo "## Host uptime"
  uptime
  echo
  echo "## Topics snapshot"
  bash "${ROOT_DIR}/scripts/check_topics.sh" || true
  echo
} > "${REPORT_FILE}"

if command -v tegrastats >/dev/null 2>&1; then
  timeout "${DURATION}s" tegrastats --interval 1000 > "${TEGRA_FILE}" 2>/dev/null || true
else
  echo "tegrastats no disponible" > "${TEGRA_FILE}"
fi

timeout "${DURATION}s" docker logs -f danet_ros2 2>&1 | grep -E 'Rendimiento topic FANet|Modelo de inferencia|cuda_mem|gpu_load|processed=' > "${PERF_FILE}" || true

{
  echo "## FPS model input"
  docker exec danet_ros2 bash -lc "source /opt/ros/humble/install/setup.bash && cd /workspace/CPGFANet/ros2_ws && source install/setup.bash && python3 /workspace/deploy/topic_fps_probe.py --duration 6 --topic /fanet/input/rgb --topic /fanet/input/thermal" || true
  echo
  echo "## FPS model output"
  docker exec danet_ros2 bash -lc "source /opt/ros/humble/install/setup.bash && cd /workspace/CPGFANet/ros2_ws && source install/setup.bash && python3 /workspace/deploy/topic_fps_probe.py --duration 6 --topic /fanet/segmentation/overlay" || true
  echo
  echo "## Person topics sample"
  docker exec danet_ros2 bash -lc "source /opt/ros/humble/install/setup.bash && cd /workspace/CPGFANet/ros2_ws && source install/setup.bash && timeout 4s ros2 topic echo /fanet/person_count --once" || true
  docker exec danet_ros2 bash -lc "source /opt/ros/humble/install/setup.bash && cd /workspace/CPGFANet/ros2_ws && source install/setup.bash && timeout 4s ros2 topic echo /fanet/person_distance --once" || true
  docker exec danet_ros2 bash -lc "source /opt/ros/humble/install/setup.bash && cd /workspace/CPGFANet/ros2_ws && source install/setup.bash && timeout 4s ros2 topic echo /fanet/person_position_robot --once" || true
  echo
  echo "## Model perf log tail"
  if [[ -s "${PERF_FILE}" ]]; then
    tail -n 20 "${PERF_FILE}"
  else
    echo "Sin lineas de rendimiento capturadas en ${DURATION}s"
  fi
  echo
  echo "## Orin tegrastats tail"
  if [[ -s "${TEGRA_FILE}" ]]; then
    tail -n 10 "${TEGRA_FILE}"
  else
    echo "Sin datos de tegrastats"
  fi
} >> "${REPORT_FILE}"

echo "Reporte guardado en: ${REPORT_FILE}"
echo "Logs auxiliares: ${TEGRA_FILE} y ${PERF_FILE}"