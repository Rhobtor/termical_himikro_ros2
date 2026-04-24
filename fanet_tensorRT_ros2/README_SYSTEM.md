# Sistema Actual

Este documento resume como queda el sistema ahora mismo despues del cambio a TensorRT y del paso de la RGB anotada a C++.

## Resumen corto

El sistema ya no usa PyTorch en el camino operativo. La inferencia principal va por TensorRT y la visualizacion anotada de RGB va por un nodo C++ dedicado.

La idea actual es:

- usar TensorRT para inferencia de FANet
- mantener ZED y Hikmicro como fuentes originales
- resincronizar RGB y termica antes de inferir
- calcular posicion y distancia con la profundidad de ZED
- publicar una sola vista anotada rapida, la RGB
- usar los topics originales para ZED y termica en visualizacion

## Flujo de datos

1. `zed_wrapper_2` publica la RGB original de la ZED en `/zed/zed_node/left/image_rect_color`
2. `fanet_rgb_bridge` convierte esa RGB a `rgb8` y la publica en `/fanet/raw/rgb`
3. `hikmicro_thermal` publica la termica original en `/fanet/raw/thermal`
4. `fanet_pair_sync` toma ambas entradas, les pone el mismo `timestamp` y publica:
   - `/fanet/input/rgb`
   - `/fanet/input/thermal`
5. `fanet_trt_topic_inference` recibe ese par sincronizado y ejecuta el engine TensorRT
6. `fanet_trt_topic_inference` publica `/fanet/person_centroid`
7. `fanet_person_pose` usa centroid + profundidad ZED para publicar:
   - `/fanet/person_distance`
   - `/fanet/person_position_robot`
   - `/fanet/person_position_camera`
8. `fanet_gui_topics` en C++ dibuja el cursor y etiquetas sobre `/fanet/input/rgb` y publica `/fanet/gui/rgb_annotated`

## Nodos activos

### Captura y normalizacion

- `zed_wrapper_2`
- `hikmicro_thermal`
- `fanet_rgb_bridge`

### Sincronizacion y deteccion

- `fanet_pair_sync`
- `fanet_trt_topic_inference`

### Posicion 3D y GUI

- `fanet_person_pose`
- `fanet_gui_topics`

## Topics mas importantes

### Entradas originales

- ZED original: `/zed/zed_node/left/image_rect_color`
- termica original: `/fanet/raw/thermal`

### Entradas sincronizadas al modelo

- RGB sincronizada: `/fanet/input/rgb`
- termica sincronizada: `/fanet/input/thermal`

### Salidas de seguimiento

- centroid: `/fanet/person_centroid`
- distancia: `/fanet/person_distance`
- posicion robot: `/fanet/person_position_robot`

### Visualizacion

- RGB anotada: `/fanet/gui/rgb_annotated`
- ZED original: `/zed/zed_node/left/image_rect_color`
- termica original: `/fanet/raw/thermal`

## Que cambió respecto al sistema anterior

- Se elimino PyTorch del camino operativo.
- La inferencia ahora usa el engine `fanet_448x352_fp16.engine`.
- La RGB anotada dejo de hacerse en Python y paso a un nodo C++.
- Ya no se prioriza la termica anotada ni los streams GUI comprimidos dentro del camino principal.
- La visualizacion se apoya en topics originales para ZED y termica y en un solo topic anotado para RGB.

## Rendimiento observado

Mediciones recientes del sistema ya montado:

- `/fanet/input/rgb`: alrededor de 21.33 FPS
- `/fanet/gui/rgb_annotated`: alrededor de 18.33 FPS
- `/zed/zed_node/left/image_rect_color`: alrededor de 23.67 FPS
- `/fanet/raw/thermal`: alrededor de 16.67 FPS

Interpretacion practica:

- la RGB anotada ya esta cerca del ritmo util del pipeline
- la inferencia TensorRT ya no es el unico cuello
- la termica y la resincronizacion condicionan el techo general del sistema

## Donde sigue habiendo coste

Los costes mas claros que aun quedan son:

- sincronizacion Python en `pair_sync_bridge.py`
- preprocesado y postprocesado Python en el nodo TensorRT
- adquisicion termica por RTSP
- posibles copias de imagen entre nodos ROS

## Ficheros clave

- `scripts/up_trt_stack.sh`: arranque completo
- `scripts/down_trt_stack.sh`: parada completa
- `configs/fanet_trt.params.yaml`: parametros del nodo TensorRT
- `ros2_ws/src/cpgfanet_trt_inference/.../topic_inference_trt_node.py`: inferencia TensorRT actual
- `ros2_ws/src/cpgfanet_trt_gui/src/rgb_person_annotator_node.cpp`: publicador C++ de RGB anotada
- `../jetson_fanet_live_stack/pair_sync_bridge.py`: resincronizacion actual RGB + termica
- `../jetson_fanet_live_stack/person_position_from_depth.py`: distancia y posicion 3D

## Vista operativa recomendada

Para trabajar dia a dia, las tres ventanas recomendadas son:

- `/fanet/gui/rgb_annotated`
- `/fanet/raw/thermal`
- `/zed/zed_node/left/image_rect_color`

El script preparado para eso es:

```bash
cd /home/isa/Documents/Luis/himikro_termical/termical_himikro_ros2/jetson_fanet_live_stack
./scripts/open_tracking_views.sh
```