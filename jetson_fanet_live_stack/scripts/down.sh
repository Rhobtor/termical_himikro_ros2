#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "${ROOT_DIR}"

docker rm -f zed_wrapper_2 hikmicro_thermal fanet_rgb_bridge fanet_pair_sync fanet_person_pose danet_ros2 >/dev/null 2>&1 || true
