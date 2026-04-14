# termical_himikro_ros2

Este repo ya no contiene solo el paquete ROS 2 de la camara termica Hikmicro.

Ahora actua como repo principal del sistema de percepcion para Jetson, con tres bloques:

## 1. Paquete ROS 2 Hikmicro

En la raiz del repo:

- `config/`
- `launch/`
- `src/`
- `CMakeLists.txt`
- `package.xml`

Incluye dos nodos para leer la camara termica Hikmicro por RTSP:

- `termical_camera` (OpenCV `VideoCapture`, backend `ffmpeg`/`gstreamer`)
- `termical_camera_ffmpeg_pipe` (lee con `ffmpeg` y publica `MONO8` por pipe)

## 2. Stack completa ZED + Hikmicro + FANet

En:

- `jetson_fanet_live_stack/`

Aqui estan:

- scripts Docker
- configuracion fija en `scripts/config.sh`
- sincronizacion RGB/termica
- visores
- persona 3D con profundidad ZED
- monitorizacion

Punto de entrada principal:

- `jetson_fanet_live_stack/README.md`

## 3. Runtime minimo de FANet para inferencia

En:

- `fanet_rso2/CPGFANet/`

Se ha copiado aqui la parte necesaria para no depender del repo FANet separado:

- `ros2_ws/src/cpgfanet_inference/`
- `docker/jetson/Dockerfile`
- `model/CrissCrossAttention_dual_2_sinINF.py`
- `model/FEANet.py`
- `weights/` (reservado para pesos)

## Build del paquete Hikmicro

Desde el workspace que contiene este repo como `src/hikmicro_thermal_camera`:

```bash
colcon build --packages-select hikmicro_thermal_camera
```

## Ejecutar nodos Hikmicro

### Opcion A: OpenCV

```bash
ros2 run hikmicro_thermal_camera termical_camera --ros-args --params-file $(ros2 pkg prefix hikmicro_thermal_camera)/share/hikmicro_thermal_camera/config/termical_camera.yaml
```

### Opcion B: ffmpeg pipe

Requiere `ffmpeg` instalado.

```bash
ros2 run hikmicro_thermal_camera termical_camera_ffmpeg_pipe --ros-args --params-file $(ros2 pkg prefix hikmicro_thermal_camera)/share/hikmicro_thermal_camera/config/termical_camera_ffmpeg_pipe.yaml
```

## Launch

```bash
ros2 launch hikmicro_thermal_camera termical_camera.launch.py
# o
ros2 launch hikmicro_thermal_camera termical_camera_ffmpeg_pipe.launch.py
```

## Siguiente lectura recomendada

- `jetson_fanet_live_stack/README.md`
- `jetson_fanet_live_stack/REPO_MAP.md`
- `jetson_fanet_live_stack/GITHUB_PUSH.md`
