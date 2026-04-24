# FANet TensorRT ROS 2

Este directorio contiene una version separada y documentada del despliegue de FANet orientada a TensorRT, sin tocar el flujo PyTorch que ya funciona en `fanet_rso2/CPGFANet`.

## Documentacion nueva

- `README_LAUNCH.md`: instrucciones para construir artefactos y lanzar la stack TensorRT actual
- `README_SYSTEM.md`: explicacion del sistema actual, nodos, topics y flujo de datos
- `README_IMPROVEMENTS.md`: mejoras posibles ordenadas por impacto y riesgo

## Objetivo

- exportar el checkpoint FEANet a ONNX
- construir un engine TensorRT fijo para Jetson
- ejecutar inferencia ROS 2 con TensorRT manteniendo el mismo preprocesado y el mismo postprocesado minimo

## Estado

- `scripts/export_fanet_onnx.py`: listo para exportar FEANet a ONNX
- `scripts/build_fanet_engine.sh`: listo para construir un engine con `trtexec`
- `scripts/build_image.sh`: construye el contenedor nuevo para export y TensorRT
- `scripts/export_onnx_docker.sh`: ejecuta el export ONNX dentro del contenedor
- `scripts/build_engine_docker.sh`: genera el `.engine` dentro del contenedor
- `scripts/config.sh`: configuracion aislada del flujo TensorRT
- `ros2_ws/src/cpgfanet_trt_inference`: esqueleto del runtime ROS 2 para TensorRT
- `Dockerfile`: base propuesta para un contenedor nuevo de TensorRT

## Limitaciones esperables

Esta version separa el trabajo, pero no garantiza todavia que FEANet exporte limpio a ONNX ni que TensorRT soporte todos los operadores sin plugins. La arquitectura usa bloques de atencion y una fusion RGB + termica personalizada, asi que el punto critico sera validar el export y el build del engine en la Jetson real.

## Flujo dockerizado

1. Construir la imagen:

```bash
./scripts/build_image.sh
```

2. Exportar ONNX dentro del contenedor:

```bash
./scripts/export_onnx_docker.sh
```

3. Construir el engine dentro del contenedor:

```bash
./scripts/build_engine_docker.sh
```

4. Lanzar el nodo TensorRT ROS 2 desde esta carpeta:

```bash
./scripts/run_trt_topic_inference_docker.sh
```

Los artefactos quedan en `artifacts/` dentro de esta carpeta.

## Flujo manual equivalente

1. Exportar ONNX:

```bash
python3 scripts/export_fanet_onnx.py \
  --repo-root /workspace/CPGFANet \
  --checkpoint /workspace/CPGFANet/weights/160.pth \
  --output /workspace/fanet_tensorRT_ros2/artifacts/fanet_448x352.onnx \
  --input-width 448 \
  --input-height 352 \
  --device cuda
```

2. Construir el engine:

```bash
./scripts/build_fanet_engine.sh \
  /workspace/fanet_tensorRT_ros2/artifacts/fanet_448x352.onnx \
  /workspace/fanet_tensorRT_ros2/artifacts/fanet_448x352_fp16.engine
```

3. Lanzar el nodo ROS 2 TensorRT con un fichero de parametros como [configs/fanet_trt.params.yaml](/home/isa/Documents/Luis/himikro_termical/termical_himikro_ros2/fanet_tensorRT_ros2/configs/fanet_trt.params.yaml).

## Estructura

- `Dockerfile`: contenedor nuevo para la rama TensorRT
- `scripts/config.sh`: rutas y parametros por defecto del flujo TensorRT
- `scripts/build_image.sh`: build de la imagen Docker TensorRT
- `scripts/export_onnx_docker.sh`: export ONNX dentro del contenedor
- `scripts/build_engine_docker.sh`: build del engine dentro del contenedor
- `scripts/run_trt_topic_inference_docker.sh`: ejecuta el nodo ROS 2 TensorRT contra los topics vivos
- `scripts/export_fanet_onnx.py`: export a ONNX
- `scripts/build_fanet_engine.sh`: build de engine con `trtexec`
- `configs/fanet_trt.params.yaml`: parametros de ejemplo
- `ros2_ws/src/cpgfanet_trt_inference`: runtime ROS 2 separado

## Siguiente validacion real

La primera prueba importante no es el nodo ROS 2 sino esta:

1. exportar ONNX sin errores
2. construir el engine TensorRT en la Jetson
3. comparar logits TensorRT vs PyTorch sobre una misma entrada

Si esa validacion pasa, la integracion ROS 2 ya es trabajo mecanico.

## Validacion conseguida hasta ahora

- ONNX exportado correctamente desde el checkpoint PyTorch
- engine FP16 generado correctamente dentro del contenedor
- inferencia TensorRT validada desde Python sobre el `.engine`

Queda como siguiente validacion de sistema ejecutar el nodo ROS 2 contra topics reales y medir FPS end-to-end.

## Notas practicas

- El `.engine` se debe generar en la Jetson objetivo o en una Jetson equivalente.
- Si la instalacion de TensorRT por `apt` falla dentro del contenedor, la alternativa correcta es partir de una imagen Jetson que ya traiga TensorRT CLI y Python.
- El riesgo principal sigue siendo la exportacion ONNX del FEANet, no el Docker en si.

