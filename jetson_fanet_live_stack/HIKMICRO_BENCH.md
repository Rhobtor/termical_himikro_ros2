# Comparar nodos Hikmicro en el mismo Docker

Abre el contenedor interactivo:

```bash
cd /home/isa/Documents/Luis/jetson_fanet_live_stack
chmod +x scripts/open_hikmicro_bench_docker.sh
chmod +x scripts/sync_hikmicro_bench_ws.sh
./scripts/sync_hikmicro_bench_ws.sh
./scripts/open_hikmicro_bench_docker.sh
```

Dentro del contenedor ya quedas con ROS 2 y el workspace Hikmicro cargados.

No hace falta reconstruir la imagen Docker cuando cambias el nodo. El benchmark usa el workspace local `hikmicro_bench_ws`, así que lo correcto es sincronizar ese `src/` y recompilarlo.

Importante: el benchmark del `ffmpeg_pipe` debe abrirse con la imagen `hikmicro_thermal_ros2:jetson`, porque esa sí incluye `/usr/bin/ffmpeg`. Si lo abres con `cpgfanet_ros2_jetson:humble`, el nodo arrancará pero la tubería se cortará al instante.

Si ya estás dentro del contenedor y quieres recompilar manualmente:

```bash
cd /workspace/hikmicro_ws
source /opt/ros/humble/install/setup.bash
colcon build --packages-select hikmicro_thermal_camera --cmake-clean-cache
source install/setup.bash
```

Importante: `source install/setup.bash` y `ros2 run ...` van en líneas separadas.

## Nodo 1: OpenCV

```bash
ros2 run hikmicro_thermal_camera termical_camera --ros-args \
  -p url:=rtsp://admin:laentiec27@192.168.2.64:554/Streaming/Channels/101 \
  -p topic_name:=/bench/thermal_opencv \
  -p fps:=25.0 \
  -p transport:=tcp \
  -p backend:=ffmpeg \
  -p force_mono:=true \
  -p publish_latest_only:=true
```

En otra shell del mismo contenedor o desde otra terminal al mismo contenedor:

```bash
docker exec -it hikmicro_bench_shell bash -lc 'source /opt/ros/humble/install/setup.bash && cd /workspace/hikmicro_ws && source install/setup.bash && python3 /workspace/deploy/topic_fps_probe.py --duration 10 --topic /bench/thermal_opencv'
```

## Nodo 2: ffmpeg pipe

Primero para el nodo anterior con `Ctrl+C`, luego ejecuta:

```bash
ros2 run hikmicro_thermal_camera termical_camera_ffmpeg_pipe --ros-args \
  -p url:=rtsp://admin:laentiec27@192.168.2.64:554/Streaming/Channels/101 \
  -p topic_name:=/bench/thermal_pipe \
  -p fps:=25.0 \
  -p transport:=tcp \
  -p width:=640 \
  -p height:=512
```

Y mide:

```bash
docker exec -it hikmicro_bench_shell bash -lc 'source /opt/ros/humble/install/setup.bash && cd /workspace/hikmicro_ws && source install/setup.bash && python3 /workspace/deploy/topic_fps_probe.py --duration 10 --topic /bench/thermal_pipe'
```

## Qué comparar

- FPS reales del topic publicado.
- Estabilidad: si hay cortes o reconexiones en consola.
- Fluidez visual si abres una vista con OpenCV o RViz.
- Latencia percibida.

## Resultado esperado en esta Jetson

- `termical_camera` con OpenCV: alrededor de `16 fps`.
- `termical_camera_ffmpeg_pipe` estable con `tcp` y sin flags agresivos: alrededor de `21.5 fps`.

Si el `ffmpeg_pipe` vuelve a cortar, asegúrate de recompilar el paquete Hikmicro con el parche nuevo y de usar `transport:=tcp`.

## Comando útil extra

Para ver si el stream abre bien con OpenCV directamente en el contenedor:

```bash
python3 - <<'PY'
import cv2
url = 'rtsp://admin:laentiec27@192.168.2.64:554/Streaming/Channels/101'
cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
print('opened', cap.isOpened())
for i in range(5):
    ok, frame = cap.read()
    print(i, ok, None if frame is None else frame.shape)
cap.release()
PY
```