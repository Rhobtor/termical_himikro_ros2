# Lanzamiento TensorRT

Este documento describe como levantar la version nueva basada en TensorRT dentro de `fanet_tensorRT_ros2`.

## Que levanta esta version

La stack actual levanta estos bloques:

- `zed_wrapper_2`: publica la RGB original de la ZED
- `hikmicro_thermal`: publica la termica original
- `fanet_rgb_bridge`: convierte la RGB de ZED a `rgb8`
- `fanet_pair_sync`: resincroniza RGB y termica con el mismo `timestamp`
- `fanet_trt_topic_inference`: ejecuta FANet con TensorRT
- `fanet_person_pose`: calcula posicion 3D y distancia con profundidad ZED
- `fanet_gui_topics`: nodo C++ que publica la RGB anotada

Las tres vistas utiles ahora son:

- RGB anotada: `/fanet/gui/rgb_annotated`
- Termica original: `/fanet/raw/thermal`
- RGB original de ZED: `/zed/zed_node/left/image_rect_color`

## Requisitos

- Jetson con Docker y `--runtime nvidia`
- ZED conectada y funcional
- camara Hikmicro accesible por RTSP
- checkpoint `160.pth` disponible en la ruta configurada
- engine TensorRT generado para esta Jetson o una equivalente

## Ficheros a revisar antes de lanzar

- `scripts/config.sh` de esta carpeta
- `../jetson_fanet_live_stack/scripts/config.sh`

Revisa sobre todo:

- `LIVE_STACK_ROOT`
- `FANET_HOST_CHECKPOINT_PATH`
- `HIKMICRO_RTSP_URL`
- `FANET_SYNC_RATE`
- `FANET_ENGINE_PATH`

## Flujo recomendado desde cero

Entra en esta carpeta:

```bash
cd /home/isa/Documents/Luis/himikro_termical/termical_himikro_ros2/fanet_tensorRT_ros2
```

Construye la imagen TensorRT, exporta ONNX y genera el engine:

```bash
./scripts/build_all_artifacts.sh
```

Levanta la stack completa TensorRT:

```bash
./scripts/up_trt_stack.sh
```

Comprueba que los topics principales existen:

```bash
./scripts/check_topics_trt.sh
```

Mira los logs del nodo TensorRT:

```bash
docker logs -f fanet_trt_topic_inference
```

Abre las tres vistas principales desde la carpeta live stack:

```bash
cd ../jetson_fanet_live_stack
./scripts/open_tracking_views.sh
```

Para parar todo:

```bash
cd ../fanet_tensorRT_ros2
./scripts/down_trt_stack.sh
```

## Flujo cuando el engine ya existe

Si el engine ya esta generado, basta con:

```bash
cd /home/isa/Documents/Luis/himikro_termical/termical_himikro_ros2/fanet_tensorRT_ros2
./scripts/up_trt_stack.sh
```

## Topics principales a vigilar

Entradas al modelo:

- `/fanet/input/rgb`
- `/fanet/input/thermal`

Salidas utiles:

- `/fanet/person_centroid`
- `/fanet/person_distance`
- `/fanet/person_position_robot`
- `/fanet/gui/rgb_annotated`

Originales para visualizacion:

- `/zed/zed_node/left/image_rect_color`
- `/fanet/raw/thermal`

## Comandos de diagnostico utiles

FPS del nodo TensorRT en logs:

```bash
docker logs -f fanet_trt_topic_inference
```

FPS de topics concretos:

```bash
docker exec fanet_rgb_bridge bash -lc 'source /opt/ros/humble/install/setup.bash && python3 /workspace/deploy/topic_fps_probe.py --duration 6 --topic /fanet/input/rgb --topic /fanet/gui/rgb_annotated --topic /zed/zed_node/left/image_rect_color --topic /fanet/raw/thermal'
```

Estado rapido de contenedores:

```bash
docker ps --format '{{.Names}}' | grep -E 'fanet_gui_topics|fanet_trt_topic_inference|fanet_pair_sync|fanet_rgb_bridge|zed_wrapper_2|hikmicro_thermal|fanet_person_pose'
```

## Notas practicas

- `up_trt_stack.sh` recompila el nodo C++ de la GUI dentro del contenedor `fanet_gui_topics` al arrancar.
- La GUI nueva ya no publica la termica anotada. Para ver la termica se usa el topic original `/fanet/raw/thermal`.
- La RGB anotada actual se publica desde un nodo C++ dedicado para reducir carga CPU y acercarse al ritmo del modelo.