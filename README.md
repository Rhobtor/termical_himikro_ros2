# hikmicro_thermal_camera

Paquete ROS 2 con **dos nodos** para leer una cámara térmica Hikmicro por RTSP:

- `termical_camera` (OpenCV `VideoCapture`, backend `ffmpeg`/`gstreamer`)
- `termical_camera_ffmpeg_pipe` (lee con `ffmpeg` y publica MONO8 por pipe)

## Build

Desde el workspace (carpeta que contiene `src/`):

```bash
colcon build --packages-select hikmicro_thermal_camera
```

## Ejecutar

### Opción A: OpenCV

```bash
ros2 run hikmicro_thermal_camera termical_camera --ros-args --params-file $(ros2 pkg prefix hikmicro_thermal_camera)/share/hikmicro_thermal_camera/config/termical_camera.yaml
```

### Opción B: ffmpeg pipe

Requiere `ffmpeg` instalado (por defecto `/usr/bin/ffmpeg`).

```bash
ros2 run hikmicro_thermal_camera termical_camera_ffmpeg_pipe --ros-args --params-file $(ros2 pkg prefix hikmicro_thermal_camera)/share/hikmicro_thermal_camera/config/termical_camera_ffmpeg_pipe.yaml
```

## Launch

```bash
ros2 launch hikmicro_thermal_camera termical_camera.launch.py
# o
ros2 launch hikmicro_thermal_camera termical_camera_ffmpeg_pipe.launch.py
```
