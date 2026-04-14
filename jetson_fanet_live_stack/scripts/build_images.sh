#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
ZED_DOCKER_DIR="${ROOT_DIR}/../zed_wrapper/zed-ros2-wrapper-humble-v4.1.4/docker"

cd "${ROOT_DIR}"

source "${ROOT_DIR}/scripts/config.sh"

echo "[1/3] Preparando fuentes de ZED para Docker"
if [[ "${ZED_BUILD}" == "1" ]]; then
	rm -rf "${ZED_DOCKER_DIR}/tmp_sources"
	mkdir -p "${ZED_DOCKER_DIR}/tmp_sources"
	cp -r "${ROOT_DIR}/../zed_wrapper/zed-ros2-wrapper-humble-v4.1.4"/zed* "${ZED_DOCKER_DIR}/tmp_sources/"
else
	echo "Saltando preparacion de fuentes ZED porque ZED_BUILD=${ZED_BUILD}"
fi

echo "[2/3] Creando directorios de salida"
mkdir -p "${FANET_OUTPUT_DIR}"

echo "[3/3] Construyendo imagenes Docker"
if [[ "${ZED_BUILD}" == "1" ]]; then
	docker build \
		-t "${ZED_IMAGE}" \
		--build-arg IMAGE_NAME="${JETSON_ROS_BASE_IMAGE}" \
		--build-arg L4T_VERSION="${L4T_VERSION}" \
		--build-arg L4T_MAJOR="${L4T_MAJOR}" \
		--build-arg L4T_MINOR="${L4T_MINOR}" \
		--build-arg ZED_SDK_MAJOR="${ZED_SDK_MAJOR}" \
		--build-arg ZED_SDK_MINOR="${ZED_SDK_MINOR}" \
		--build-arg ZED_SDK_PATCH="${ZED_SDK_PATCH}" \
		-f "${ZED_DOCKER_DIR}/Dockerfile.l4t-humble" \
		"${ZED_DOCKER_DIR}"
else
	echo "Saltando build de ZED. Usando imagen existente: ${ZED_IMAGE}"
fi

if [[ "${HIKMICRO_BUILD}" == "1" ]]; then
	docker build \
		-t "${HIKMICRO_IMAGE}" \
		--build-arg BASE_IMAGE="${FANET_IMAGE}" \
		-f "${ROOT_DIR}/Dockerfile.hikmicro" \
		"${ROOT_DIR}/.."
else
	echo "Saltando build de Hikmicro. Usando imagen existente: ${HIKMICRO_IMAGE}"
fi

if [[ "${FANET_BUILD}" == "1" ]]; then
	docker build \
		-t "${FANET_IMAGE}" \
		--build-arg BASE_IMAGE="${FANET_BASE_IMAGE}" \
		-f "${ROOT_DIR}/../fanet_rso2/CPGFANet/docker/jetson/Dockerfile" \
		"${ROOT_DIR}/../fanet_rso2/CPGFANet"
else
	echo "Saltando build de FANet. Usando imagen existente: ${FANET_IMAGE}"
fi

echo "Imagenes listas."
