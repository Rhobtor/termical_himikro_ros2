# Stack live ZED + Hikmicro + FANet para Jetson

Este directorio ahora vive dentro del repo principal `termical_himikro_ros2`, que pasa a contener:

- el paquete ROS 2 de la camara termica Hikmicro
- esta stack de despliegue Docker y ROS 2
- una copia local de la parte minima de FANet necesaria para inferencia

Con esto ya no hace falta depender de varios repos separados para la parte principal del sistema.

Este directorio ya no es solo un conjunto de scripts sueltos: contiene el despliegue operativo, utilidades de medicion, visores y nodos auxiliares para persona 3D.

Si quieres orientarte rapido antes de tocar nada, lee tambien:

- `REPO_MAP.md`: donde esta cada cosa y para que sirve.
- `GITHUB_PUSH.md`: como versionarlo y subirlo a GitHub.
- `HIKMICRO_BENCH.md`: flujo de benchmark del nodo termico.

Este despliegue deja tres entradas ROS 2 conectadas por Docker:

- `zed_wrapper_2` publica RGB desde ZED.
- `fanet_rgb_bridge` adapta el topic RGB de ZED a `rgb8` en `/fanet/input/rgb`.
- `hikmicro_thermal` publica la térmica en `/fanet/raw/thermal` usando `ffmpeg` dentro del contenedor.
- `fanet_pair_sync` republica RGB y térmica con un mismo `timestamp` para que FANet procese pares reales.
- `danet_ros2` consume ambos topics y ejecuta la inferencia de FANet.

## Topics finales usados por FANet

- RGB: `/fanet/input/rgb`
- Térmica: `/fanet/input/thermal`

## Topics intermedios

- RGB bruto normalizado: `/fanet/raw/rgb`
- Térmica bruta: `/fanet/raw/thermal`
- Térmica bruta comprimida: `/fanet/raw/thermal/compressed`

## Topics de salida

- `/fanet/segmentation/mask_indices`
- `/fanet/segmentation/mask_color`
- `/fanet/segmentation/overlay`
- `/fanet/person_centroid`
- `/fanet/person_centroids`
- `/fanet/person_count`
- `/fanet/person_position_camera`
- `/fanet/person_positions_camera`
- `/fanet/person_position_robot`
- `/fanet/person_distance`
- `/fanet/person_positions_robot`
- `/fanet/person_distances`
- `/fanet/gui/rgb_annotated`
- `/fanet/gui/thermal_annotated`
- `/fanet/gui/rgb_annotated/compressed`
- `/fanet/gui/thermal_annotated/compressed`

`/fanet/person_centroid` no da distancia real. Publica:

- `x`: pixel horizontal del centro de la persona en la salida del modelo
- `y`: pixel vertical del centro de la persona en la salida del modelo
- `z`: area segmentada en pixeles

La distancia y posicion 3D reales se publican en:

- `/fanet/person_position_camera`: `geometry_msgs/PointStamped` en frame optico de camara
- `/fanet/person_positions_camera`: `geometry_msgs/PoseArray` con una entrada por cada deteccion en el mismo orden de `/fanet/person_centroids`
- `/fanet/person_position_robot`: `geometry_msgs/PointStamped` en frame tipo robot con mismo origen y ejes `x` delante, `y` izquierda, `z` arriba
- `/fanet/person_distance`: `std_msgs/Float32` con distancia euclidea en metros
- `/fanet/person_positions_robot`: `geometry_msgs/PoseArray` con posicion local de todas las personas detectadas
- `/fanet/person_distances`: `std_msgs/Float32MultiArray` con una distancia por cada persona detectada

Para la GUI tambien quedan disponibles:

- `/fanet/gui/rgb_annotated`: imagen RGB de ZED con todas las personas detectadas anotadas
- `/fanet/gui/thermal_annotated`: imagen termica coloreada con las mismas anotaciones
- `/fanet/gui/rgb_annotated/compressed`: version JPEG para enlaces VPN o bajo ancho de banda
- `/fanet/gui/thermal_annotated/compressed`: version JPEG para enlaces VPN o bajo ancho de banda

Para transmision remota conviene priorizar:

- `/zed/zed_node/left/image_rect_color/compressed` para RGB original de ZED
- `/fanet/raw/thermal/compressed` para termica original
- `/fanet/gui/rgb_annotated/compressed` y `/fanet/gui/thermal_annotated/compressed` para la GUI
- `/fanet/person_centroids`, `/fanet/person_positions_robot` y `/fanet/person_distances` para datos ligeros de seguimiento

## Arranque

Desde esta carpeta:

```bash
chmod +x scripts/*.sh
./scripts/up.sh
```

Los scripts usan `docker build` y `docker run` directos, así que no dependen del plugin `docker compose`.

## Estructura del codigo

### Configuracion

- `scripts/config.sh`: configuracion fija de la stack. Aqui estan RTSP, topics, imagenes y rutas.
- `fanet_fast.params.yaml`: perfil rapido del modelo, recomendado para tiempo real.
- `fanet_live.params.yaml`: perfil mas pesado, mas cerca del flujo original.

### Pesos del modelo

- El checkpoint esperado es `160.pth`.
- Debe existir en `../fanet_rso2/CPGFANet/weights/160.pth`.
- `scripts/up.sh` monta esa carpeta dentro del contenedor y falla con un mensaje claro si falta el archivo.
- Para cambiar el nombre o la ruta, edita `FANET_CHECKPOINT_NAME` o `FANET_HOST_WEIGHTS_DIR` en `scripts/config.sh`.

### Nodos auxiliares del despliegue

- `rgb_topic_adapter.py`: adapta el topic RGB de ZED a `rgb8`.
- `thermal_rtsp_publisher.py`: publica la imagen termica desde RTSP.
- `thermal_rtsp_publisher.py`: publica la termica en crudo y en JPEG comprimido.
- `pair_sync_bridge.py`: resincroniza RGB y termica para que FANet procese pares validos.
- `person_position_from_depth.py`: convierte cada deteccion 2D de persona a posicion 3D y distancia usando ZED.
- `gui_topics_publisher.py`: publica RGB y termica anotados para consumirlos desde una GUI remota.
- `gui_topics_publisher.py`: publica RGB y termica anotados tanto en crudo como comprimidos.
- `person_overlay_viewer.py`: visor con overlay y personas dibujadas.
- `topic_fps_probe.py`: utilidad de medida de FPS ROS 2.

### Scripts operativos

- `scripts/up.sh`: arranque completo.
- `scripts/down.sh`: parada completa.
- `scripts/check_topics.sh`: comprobacion rapida de topics y publishers.
- `scripts/monitor_fanet.sh`: metricas de rendimiento.
- `scripts/open_fanet_viewers.sh`: visor de termica y overlay.
- `scripts/open_person_overlay_viewer.sh`: visor overlay con varias personas.
- `scripts/open_hikmicro_bench_docker.sh`: Docker de benchmark Hikmicro.
- `scripts/sync_hikmicro_bench_ws.sh`: sincronizacion del workspace de benchmark.

## Verificación

```bash
./scripts/check_topics.sh
./scripts/logs.sh danet_ros2
./scripts/logs.sh zed_wrapper_2
./scripts/logs.sh hikmicro_thermal
./scripts/open_fanet_viewers.sh
./scripts/open_person_overlay_viewer.sh
./scripts/capture_runtime_report.sh 15
./scripts/monitor_fanet.sh stats
./scripts/monitor_fanet.sh stats-once
./scripts/monitor_fanet.sh perf
./scripts/monitor_fanet.sh jetson
./scripts/monitor_fanet.sh jetson-once
./scripts/monitor_fanet.sh fps-capture
./scripts/monitor_fanet.sh fps-model
./scripts/monitor_fanet.sh fps-output
./scripts/monitor_fanet.sh snapshot
```

## Qué mide cada modo

- `stats`: uso en vivo por contenedor con `docker stats`.
- `stats-once`: foto rápida de CPU y RAM por contenedor.
- `jetson`: consumo en vivo de la Jetson host con `tegrastats`.
- `jetson-once`: foto rápida de CPU, RAM y carga del host.
- `perf`: tiempos del modelo cuando FANet ya está procesando pares: total, preprocess, infer, post, FPS medio, memoria CUDA y carga GPU si el nodo la logra leer.
- `fps-capture`: FPS de captura bruta, antes del sincronizador.
- `fps-model`: FPS con los topics que entran realmente al modelo.
- `fps-output`: FPS de la salida `overlay` del modelo.
- `snapshot`: resumen corto combinando Docker, host Jetson y FPS de entrada al modelo.

## Parada

```bash
./scripts/down.sh
```

## Compose opcional

Se incluye `docker-compose.yml` como referencia y para hosts donde sí exista Compose, pero el flujo principal validado aquí es con los scripts de `scripts/`.

## Variables a revisar antes de usar

Edita `scripts/config.sh` si necesitas cambiar:

- `ZED_CAMERA_MODEL`
- `ZED_RGB_TOPIC`
- `HIKMICRO_RTSP_URL`
- `ROS_DOMAIN_ID`
- `FANET_PARAMS_FILE` para elegir entre perfil estable y perfil rapido
- `FANET_HOST_WEIGHTS_DIR` y `FANET_CHECKPOINT_NAME` para la ruta del checkpoint
- `L4T_VERSION`, `L4T_MAJOR` y `L4T_MINOR` si tu JetPack cambia

## Nota importante

El nodo de inferencia de FANet no soporta `bgra8`, por eso se añadió `rgb_topic_adapter.py` para convertir el topic RGB de ZED a `rgb8` antes de la inferencia.

En esta máquina el build ROS original del nodo Hikmicro quedaba bloqueado por una clave GPG expirada del repositorio ROS dentro de la imagen base. Para dejar el stack utilizable ya, el contenedor térmico se resolvió con un publicador RTSP equivalente en Python más `ffmpeg`, manteniendo el mismo topic final `/fanet/input/thermal`.

Además, como RGB y térmica no nacen con el mismo `timestamp`, se añadió `pair_sync_bridge.py` para republicarlas con sello temporal común antes de entrar a FANet. Sin eso, el nodo de inferencia no procesaba pares de forma consistente.

## Estado actual del repo unificado

Dentro de este mismo repo ahora existen tambien:

- `../fanet_rso2/CPGFANet`: copia local del runtime minimo de FANet para inferencia
- `../config`, `../launch`, `../src`: paquete Hikmicro original/parcheado

Lo unico que sigue fuera por defecto es la fuente de ZED wrapper si decides reconstruir la imagen ZED desde cero. Si `ZED_BUILD=0`, el flujo normal no necesita ese repo externo.

