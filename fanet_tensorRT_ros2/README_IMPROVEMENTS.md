# Posibles Mejoras

Este documento agrupa cambios posibles para seguir mejorando el sistema actual basado en TensorRT.

## Prioridad alta

### 1. Pasar el nodo TensorRT completo a C++

Impacto esperado: alto.

Ahora mismo la GPU ya corre por TensorRT, pero aun quedan en Python:

- recepcion de mensajes ROS
- conversion de imagen a `numpy`
- resize y normalizacion
- apilado de canales RGB + termica
- postproceso para extraer la persona principal

Mover todo eso a C++ reduciria:

- uso de CPU
- jitter
- copias de memoria
- latencia entre etapas

Este es el cambio con mejor balance entre complejidad e impacto general.

### 2. Reemplazar `pair_sync_bridge.py` por un sincronizador C++

Impacto esperado: alto.

El sincronizador actual hace `copy.deepcopy` de cada frame antes de publicar. Eso mete coste extra y no ayuda a la latencia.

Una version C++ o una integracion directa dentro del nodo de inferencia permitiria:

- menos copias
- menos serializacion ROS intermedia
- menos CPU
- menos puntos de bloqueo

### 3. Probar engine INT8

Impacto esperado: medio a alto, con riesgo de precision.

Ahora el engine operativo es FP16. Si la precision aguanta con calibracion realista, INT8 puede subir el rendimiento de inferencia y reducir coste de memoria.

Antes de adoptarlo haria falta validar:

- IoU o calidad de mascara sobre escenas reales
- centroid y distancia resultantes
- estabilidad en escenas con varias personas o fondos termicos complejos

## Prioridad media

### 4. Integrar sincronizacion + inferencia + salida en un unico nodo

Impacto esperado: medio a alto.

La idea es unir en un solo proceso:

- entrada RGB
- entrada termica
- emparejado temporal
- preproceso
- TensorRT
- postproceso
- publicacion de centroid

Eso simplifica la arquitectura y reduce saltos entre nodos.

### 5. Mejorar la adquisicion termica

Impacto esperado: medio, pero puede definir el techo real.

Ahora la termica llega por RTSP. Si ese flujo no mantiene FPS o mete jitter, el pipeline entero queda limitado por esa rama.

Cambios posibles:

- probar UDP en vez de TCP
- revisar parametros del nodo Hikmicro actual
- evitar recompresiones
- mantener `mono8` hasta el ultimo momento
- usar un acceso mas directo a la camara si existe SDK estable para Jetson

### 6. Revisar la configuracion del wrapper ZED

Impacto esperado: medio.

La ZED original ya da bastante FPS, pero conviene revisar si se esta pidiendo mas de lo necesario.

Cambios posibles:

- resolucion de captura
- FPS de captura
- topics no usados
- coste del depth y configuracion asociada

Si el sistema final solo necesita cierto rango de FPS, simplificar el wrapper puede liberar CPU y ancho de banda.

## Prioridad baja o condicional

### 7. Publicacion remota comprimida separada

Impacto esperado: bajo en pipeline local, util en teleoperacion.

Si luego se necesita visualizacion remota por red, conviene separar eso del pipeline local. La idea seria:

- mantener topics internos sin compresion
- crear solo para remoto una rama `compressed`
- no meter JPEG en el camino principal

### 8. Mas salidas GUI solo si hacen falta

Impacto esperado: bajo o negativo si se abusa.

La experiencia reciente ya enseño que publicar mas imagenes anotadas, termicas anotadas o JPEG dentro del mismo camino empeora el rendimiento general. Solo merece la pena si hay una necesidad clara de operador.

## Cambios concretos que yo haria en orden

1. Nodo TensorRT completo en C++.
2. Sincronizador C++ o fusion del sincronizador dentro del nodo TensorRT.
3. Evaluacion FP16 vs INT8 con escenas reales.
4. Afinar la rama termica para reducir jitter y elevar su FPS real.
5. Revisar wrapper ZED y profundidad para no pagar trabajo innecesario.

## Cambios que no priorizaria ahora

- volver a PyTorch
- meter de nuevo GUI termica anotada en el camino principal
- aumentar resolucion del modelo sin necesidad clara
- comprimir JPEG dentro del pipeline local

## Criterio para decidir el siguiente paso

Si el objetivo es mas FPS del modelo y menos latencia total, el siguiente paso correcto no es tocar la GUI otra vez. El siguiente paso correcto es eliminar el Python que aun queda en el camino de sincronizacion e inferencia.