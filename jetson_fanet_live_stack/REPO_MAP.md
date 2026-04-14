# Mapa del Proyecto

Esta carpeta contiene el despliegue ROS 2 + Docker que une ZED, Hikmicro y FANet en Jetson.

## Que vive en este repo

- `README.md`: vision general, arranque, verificacion y topics.
- `REPO_MAP.md`: mapa rapido de archivos y responsabilidades.
- `GITHUB_PUSH.md`: pasos para inicializar Git y subir a GitHub.
- `scripts/config.sh`: configuracion principal fija del stack.
- `fanet_fast.params.yaml`: perfil rapido del modelo, pensado para mantener alrededor de 6 fps.
- `fanet_live.params.yaml`: perfil mas pesado/original del modelo.
- `docker-compose.yml`: referencia, no es el flujo principal validado.

## Nodos Python propios de este despliegue

- `rgb_topic_adapter.py`: convierte el RGB de ZED a `rgb8`.
- `thermal_rtsp_publisher.py`: publica la termica Hikmicro desde RTSP usando `ffmpeg`.
- `pair_sync_bridge.py`: resincroniza RGB y termica con el mismo timestamp para FANet.
- `topic_fps_probe.py`: mide FPS de topics ROS 2.
- `person_position_from_depth.py`: usa la profundidad ZED para convertir la deteccion 2D en posicion 3D y distancia.
- `person_overlay_viewer.py`: visor del overlay con centroides de personas dibujados.

## Scripts operativos

- `scripts/up.sh`: arranca toda la stack.
- `scripts/down.sh`: para toda la stack.
- `scripts/check_topics.sh`: revisa entradas, salidas y topics de persona.
- `scripts/logs.sh`: sigue logs de un contenedor.
- `scripts/monitor_fanet.sh`: metricas de Docker, Jetson, entrada y salida del modelo.
- `scripts/open_fanet_viewers.sh`: abre visores de termica y overlay.
- `scripts/open_person_overlay_viewer.sh`: abre visor overlay con personas.
- `scripts/open_hikmicro_bench_docker.sh`: abre Docker interactivo para benchmark Hikmicro.
- `scripts/sync_hikmicro_bench_ws.sh`: sincroniza el workspace de benchmark Hikmicro con el repo real.
- `scripts/build_images.sh`: construccion opcional de imagenes.

## Repos externos modificados durante el trabajo

Estos cambios no viven en esta carpeta. Si quieres conservar todo, tambien debes revisar estos repos:

- `../fanet_rso2/CPGFANet`
  - `ros2_ws/src/cpgfanet_inference/cpgfanet_inference/topic_inference_node.py`
  - Aqui se mejoro el postproceso para separar personas por componentes conectados, publicar centroides multiples y mantener el rendimiento.

- `../himikro_termical/termical_himikro_ros2`
  - `config/termical_camera.yaml`
  - `config/termical_camera_ffmpeg_pipe.yaml`
  - `src/termical_hikmicro.cpp`
  - `src/termical_hikmicro_ffmpeg_pipe.cpp`
  - Aqui se corrigio la IP RTSP, compatibilidad con OpenCV y el comando `ffmpeg_pipe` estable.

## Flujo recomendado de versionado

1. Esta carpeta ya vive dentro del repo principal `termical_himikro_ros2`.
2. La configuracion de despliegue esta en `scripts/config.sh`, no en `.env`.
3. No mezclar benchmarks temporales ni `__pycache__`.