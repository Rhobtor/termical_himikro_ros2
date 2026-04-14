from __future__ import annotations

import atexit
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Deque

import cv2
import numpy as np
import rclpy
from geometry_msgs.msg import Pose, PoseArray
from geometry_msgs.msg import PointStamped
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import Int32
import torch

from .model_runtime import (
    blend_overlay,
    colorize_mask,
    configure_torch_runtime,
    default_repo_root,
    load_model,
    predict_mask,
    preprocess_pair,
    save_outputs,
)


class TopicInferenceNode(Node):
    def __init__(self) -> None:
        super().__init__('cpgfanet_topic_inference')

        self.declare_parameter('repo_root', str(default_repo_root()))
        self.declare_parameter('checkpoint_path', '')
        self.declare_parameter('model_module', 'model.FEANet')
        self.declare_parameter('model_class', 'FEANet')
        self.declare_parameter('device', 'cuda')
        self.declare_parameter('input_width', 640)
        self.declare_parameter('input_height', 480)
        self.declare_parameter('num_classes', 9)
        self.declare_parameter('rgb_scale', 255.0)
        self.declare_parameter('thermal_scale', 255.0)
        self.declare_parameter('overlay_alpha', 0.45)
        self.declare_parameter('rgb_topic', 'fanet/input/rgb')
        self.declare_parameter('thermal_topic', 'fanet/input/thermal')
        self.declare_parameter('mask_topic', 'fanet/segmentation/mask_indices')
        self.declare_parameter('color_topic', 'fanet/segmentation/mask_color')
        self.declare_parameter('overlay_topic', 'fanet/segmentation/overlay')
        self.declare_parameter('person_centroid_topic', 'fanet/person_centroid')
        self.declare_parameter('person_centroids_topic', 'fanet/person_centroids')
        self.declare_parameter('person_count_topic', 'fanet/person_count')
        self.declare_parameter('publish_mask', True)
        self.declare_parameter('publish_color', True)
        self.declare_parameter('publish_overlay', True)
        self.declare_parameter('publish_person_centroid', True)
        self.declare_parameter('publish_person_centroids', True)
        self.declare_parameter('publish_person_count', True)
        self.declare_parameter('person_class_index', 2)
        self.declare_parameter('person_min_pixels', 25)
        self.declare_parameter('draw_person_instances', True)
        self.declare_parameter('save_outputs', False)
        self.declare_parameter('output_dir', '/tmp/cpgfanet_topic_outputs')
        self.declare_parameter('enable_perf_logging', True)
        self.declare_parameter('perf_log_period_s', 5.0)
        self.declare_parameter('perf_window', 50)
        self.declare_parameter('perf_warmup_runs', 3)
        self.declare_parameter('enable_amp', False)
        self.declare_parameter('enable_cudnn_benchmark', True)
        self.declare_parameter('enable_cuda_sync_timing', False)
        self.declare_parameter('max_pending_pairs', 2)
        self.declare_parameter('enable_gpu_telemetry', True)

        self._device = None
        self._model = None
        self._image_size = (
            int(self.get_parameter('input_width').value),
            int(self.get_parameter('input_height').value),
        )
        self._overlay_alpha = float(self.get_parameter('overlay_alpha').value)
        self._save_outputs = bool(self.get_parameter('save_outputs').value)
        self._output_dir = Path(str(self.get_parameter('output_dir').value))
        self._enable_amp = False
        self._enable_cuda_sync_timing = bool(self.get_parameter('enable_cuda_sync_timing').value)
        self._tegrastats_proc = None
        self._tegrastats_thread = None
        self._gpu_util_percent = None
        self._gpu_freq_percent = None
        self._last_tegrastats_line = None
        self._last_inference_ms = 0.0
        self._last_total_ms = 0.0
        self._last_preprocess_ms = 0.0
        self._last_postprocess_ms = 0.0
        self._processed_pairs_at_last_log = 0
        self._last_processed_time = time.perf_counter()

        perf_window = max(2, int(self.get_parameter('perf_window').value))
        self._preprocess_times_ms = deque(maxlen=perf_window)
        self._inference_times_ms = deque(maxlen=perf_window)
        self._postprocess_times_ms = deque(maxlen=perf_window)
        self._total_times_ms = deque(maxlen=perf_window)
        self._run_count = 0
        self._processed_pairs = 0
        self._received_rgb = 0
        self._received_thermal = 0
        self._dropped_pending = 0
        self._last_perf_log = time.perf_counter()

        self._pending_rgb = {}
        self._pending_thermal = {}

        self.mask_pub = self.create_publisher(Image, str(self.get_parameter('mask_topic').value), 1)
        self.color_pub = self.create_publisher(Image, str(self.get_parameter('color_topic').value), 1)
        self.overlay_pub = self.create_publisher(Image, str(self.get_parameter('overlay_topic').value), 1)
        self.person_centroid_pub = self.create_publisher(
            PointStamped,
            str(self.get_parameter('person_centroid_topic').value),
            1,
        )
        self.person_centroids_pub = self.create_publisher(
            PoseArray,
            str(self.get_parameter('person_centroids_topic').value),
            1,
        )
        self.person_count_pub = self.create_publisher(
            Int32,
            str(self.get_parameter('person_count_topic').value),
            1,
        )

        sensor_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
        )
        self.create_subscription(Image, str(self.get_parameter('rgb_topic').value), self._on_rgb, sensor_qos)
        self.create_subscription(Image, str(self.get_parameter('thermal_topic').value), self._on_thermal, sensor_qos)

        self._start_gpu_telemetry()
        self._ensure_runtime_ready()

    def destroy_node(self):
        self._stop_gpu_telemetry()
        return super().destroy_node()

    def _ensure_runtime_ready(self) -> None:
        if self._model is not None:
            return

        repo_root = Path(str(self.get_parameter('repo_root').value))
        checkpoint_path = Path(str(self.get_parameter('checkpoint_path').value))
        device_name = str(self.get_parameter('device').value)
        if device_name == 'cuda':
            device_name = 'cuda:0'
        if device_name.startswith('cuda') and not torch.cuda.is_available():
            self.get_logger().warning('CUDA no esta disponible. Cambio automatico a CPU.')
            device_name = 'cpu'

        configure_torch_runtime(bool(self.get_parameter('enable_cudnn_benchmark').value))

        self._device = torch.device(device_name)
        self._enable_amp = bool(self.get_parameter('enable_amp').value) and self._device.type == 'cuda'
        self._model = load_model(
            repo_root=repo_root,
            checkpoint_path=checkpoint_path,
            model_module=str(self.get_parameter('model_module').value),
            model_class=str(self.get_parameter('model_class').value),
            num_classes=int(self.get_parameter('num_classes').value),
            device=self._device,
        )
        self.get_logger().info(f'Modelo de inferencia por topico cargado en {self._device}.')

    def _start_gpu_telemetry(self) -> None:
        if not bool(self.get_parameter('enable_gpu_telemetry').value):
            return
        tegrastats_path = shutil.which('tegrastats')
        if tegrastats_path is None:
            self.get_logger().warning('tegrastats no disponible. Se mostrara solo memoria CUDA.')
            return

        try:
            self._tegrastats_proc = subprocess.Popen(
                [tegrastats_path, '--interval', '1000'],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except Exception as exc:
            self.get_logger().warning(f'No se pudo arrancar tegrastats: {exc}')
            self._tegrastats_proc = None
            return

        self._tegrastats_thread = threading.Thread(target=self._read_tegrastats_loop, daemon=True)
        self._tegrastats_thread.start()
        atexit.register(self._stop_gpu_telemetry)

    def _stop_gpu_telemetry(self) -> None:
        proc = self._tegrastats_proc
        if proc is None:
            return
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                proc.kill()
        self._tegrastats_proc = None

    def _read_tegrastats_loop(self) -> None:
        proc = self._tegrastats_proc
        if proc is None or proc.stdout is None:
            return

        for line in proc.stdout:
            self._last_tegrastats_line = line.strip()
            match = re.search(r'GR3D_FREQ\s+(\d+)%', line)
            if match is not None:
                self._gpu_util_percent = float(match.group(1))

            match = re.search(r'GR3D_FREQ\s+\d+%@\[(.*?)\]', line)
            if match is not None:
                freqs = [part.strip().rstrip('%') for part in match.group(1).split(',') if part.strip()]
                try:
                    if freqs:
                        self._gpu_freq_percent = sum(float(value) for value in freqs) / len(freqs)
                except ValueError:
                    self._gpu_freq_percent = None

    def _sync_device(self) -> None:
        if not self._enable_cuda_sync_timing:
            return
        if self._device is not None and self._device.type == 'cuda' and torch.cuda.is_available():
            torch.cuda.synchronize(self._device)

    @staticmethod
    def _stamp_to_key(msg: Image) -> int:
        return int(msg.header.stamp.sec) * 1_000_000_000 + int(msg.header.stamp.nanosec)

    @staticmethod
    def _avg_ms(samples: Deque[float]) -> float:
        if not samples:
            return 0.0
        return float(sum(samples) / len(samples))

    def _trim_pending(self) -> None:
        max_pending = max(1, int(self.get_parameter('max_pending_pairs').value))
        while len(self._pending_rgb) > max_pending:
            oldest_key = min(self._pending_rgb)
            self._pending_rgb.pop(oldest_key, None)
            self._dropped_pending += 1
        while len(self._pending_thermal) > max_pending:
            oldest_key = min(self._pending_thermal)
            self._pending_thermal.pop(oldest_key, None)
            self._dropped_pending += 1

    def _on_rgb(self, msg: Image) -> None:
        key = self._stamp_to_key(msg)
        self._received_rgb += 1
        self._pending_rgb[key] = msg
        self._trim_pending()
        self._maybe_process_pair(key)

    def _on_thermal(self, msg: Image) -> None:
        key = self._stamp_to_key(msg)
        self._received_thermal += 1
        self._pending_thermal[key] = msg
        self._trim_pending()
        self._maybe_process_pair(key)

    def _maybe_process_pair(self, key: int) -> None:
        rgb_msg = self._pending_rgb.pop(key, None)
        thermal_msg = self._pending_thermal.pop(key, None)
        if rgb_msg is None or thermal_msg is None:
            if rgb_msg is not None:
                self._pending_rgb[key] = rgb_msg
            if thermal_msg is not None:
                self._pending_thermal[key] = thermal_msg
            return

        self._process_pair(rgb_msg=rgb_msg, thermal_msg=thermal_msg)

    def _process_pair(self, rgb_msg: Image, thermal_msg: Image) -> None:
        total_start = time.perf_counter()

        preprocess_start = time.perf_counter()
        rgb_image = self._image_msg_to_numpy(rgb_msg)
        thermal_image = self._image_msg_to_numpy(thermal_msg)
        input_tensor, rgb_resized, _ = preprocess_pair(
            rgb_image=rgb_image,
            thermal_image=thermal_image,
            image_size=self._image_size,
            rgb_scale=float(self.get_parameter('rgb_scale').value),
            thermal_scale=float(self.get_parameter('thermal_scale').value),
        )
        preprocess_end = time.perf_counter()

        self._sync_device()
        inference_start = time.perf_counter()
        mask = predict_mask(
            model=self._model,
            input_tensor=input_tensor,
            device=self._device,
            use_amp=self._enable_amp,
        )
        self._sync_device()
        inference_end = time.perf_counter()

        postprocess_start = time.perf_counter()
        person_instances = self._extract_person_instances(mask)
        primary_person = person_instances[0] if person_instances else None

        color_mask = None
        overlay = None
        if bool(self.get_parameter('publish_color').value) or bool(self.get_parameter('publish_overlay').value) or self._save_outputs:
            color_mask = colorize_mask(mask)
        if bool(self.get_parameter('publish_overlay').value) or self._save_outputs:
            overlay = blend_overlay(rgb_image=rgb_resized, color_mask=color_mask, alpha=self._overlay_alpha)
            if bool(self.get_parameter('draw_person_instances').value) and person_instances:
                overlay = self._draw_person_instances(overlay, person_instances)

        stamp = rgb_msg.header.stamp
        frame_id = rgb_msg.header.frame_id or f'frame_{self._processed_pairs:06d}'
        if bool(self.get_parameter('publish_person_centroid').value) and primary_person is not None:
            self.person_centroid_pub.publish(self._centroid_to_point(primary_person, stamp, frame_id))
        if bool(self.get_parameter('publish_person_centroids').value):
            self.person_centroids_pub.publish(self._centroids_to_pose_array(person_instances, stamp, frame_id))
        if bool(self.get_parameter('publish_person_count').value):
            count_msg = Int32()
            count_msg.data = len(person_instances)
            self.person_count_pub.publish(count_msg)
        if bool(self.get_parameter('publish_mask').value):
            self.mask_pub.publish(self._numpy_to_image(mask, 'mono8', stamp, frame_id))
        if bool(self.get_parameter('publish_color').value) and color_mask is not None:
            self.color_pub.publish(self._numpy_to_image(color_mask, 'rgb8', stamp, frame_id))
        if bool(self.get_parameter('publish_overlay').value) and overlay is not None:
            self.overlay_pub.publish(self._numpy_to_image(overlay, 'rgb8', stamp, frame_id))

        if self._save_outputs and color_mask is not None and overlay is not None:
            save_outputs(
                output_dir=self._output_dir / frame_id,
                mask=mask,
                color_mask=color_mask,
                overlay=overlay,
            )
        postprocess_end = time.perf_counter()

        self._record_run_stats(
            preprocess_ms=(preprocess_end - preprocess_start) * 1000.0,
            inference_ms=(inference_end - inference_start) * 1000.0,
            postprocess_ms=(postprocess_end - postprocess_start) * 1000.0,
            total_ms=(postprocess_end - total_start) * 1000.0,
        )
        self._processed_pairs += 1

    def _record_run_stats(
        self,
        preprocess_ms: float,
        inference_ms: float,
        postprocess_ms: float,
        total_ms: float,
    ) -> None:
        self._run_count += 1
        self._last_preprocess_ms = preprocess_ms
        self._last_inference_ms = inference_ms
        self._last_postprocess_ms = postprocess_ms
        self._last_total_ms = total_ms
        self._last_processed_time = time.perf_counter()
        if self._run_count <= max(0, int(self.get_parameter('perf_warmup_runs').value)):
            return

        self._preprocess_times_ms.append(preprocess_ms)
        self._inference_times_ms.append(inference_ms)
        self._postprocess_times_ms.append(postprocess_ms)
        self._total_times_ms.append(total_ms)
        self._maybe_log_performance()

    def _maybe_log_performance(self) -> None:
        if not bool(self.get_parameter('enable_perf_logging').value):
            return
        if not self._total_times_ms:
            return

        now = time.perf_counter()
        if (now - self._last_perf_log) < max(0.5, float(self.get_parameter('perf_log_period_s').value)):
            return

        avg_total_ms = self._avg_ms(self._total_times_ms)
        avg_pre_ms = self._avg_ms(self._preprocess_times_ms)
        avg_inf_ms = self._avg_ms(self._inference_times_ms)
        avg_post_ms = self._avg_ms(self._postprocess_times_ms)
        fps = 1000.0 / avg_total_ms if avg_total_ms > 1e-6 else 0.0
        elapsed = max(now - self._last_perf_log, 1e-6)
        processed_since_last = self._processed_pairs - self._processed_pairs_at_last_log
        output_fps = processed_since_last / elapsed
        input_rgb_fps = self._received_rgb / max(now - self._last_processed_time + elapsed, 1e-6)
        input_tir_fps = self._received_thermal / max(now - self._last_processed_time + elapsed, 1e-6)
        gpu_memory_msg = self._build_gpu_memory_message()
        gpu_load_msg = self._build_gpu_load_message()

        self.get_logger().info(
            'Rendimiento topic FANet | total={:.1f} ms | preprocess={:.1f} ms | infer={:.1f} ms | post={:.1f} ms | fps_avg={:.2f} | fps_out={:.2f} | last_total={:.1f} ms | last_infer={:.1f} ms | processed={} | rgb_rx={} | tir_rx={} | dropped={}{}{}'.format(
                avg_total_ms,
                avg_pre_ms,
                avg_inf_ms,
                avg_post_ms,
                fps,
                output_fps,
                self._last_total_ms,
                self._last_inference_ms,
                self._processed_pairs,
                self._received_rgb,
                self._received_thermal,
                self._dropped_pending,
                gpu_memory_msg,
                gpu_load_msg,
            )
        )
        self._processed_pairs_at_last_log = self._processed_pairs
        self._last_perf_log = now

    def _extract_person_instances(self, mask: np.ndarray):
        person_class_index = int(self.get_parameter('person_class_index').value)
        min_pixels = max(1, int(self.get_parameter('person_min_pixels').value))
        binary = (mask == person_class_index).astype(np.uint8)
        if not np.any(binary):
            return []

        component_count, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
        instances = []
        for label in range(1, component_count):
            area = int(stats[label, cv2.CC_STAT_AREA])
            if area < min_pixels:
                continue
            left = int(stats[label, cv2.CC_STAT_LEFT])
            top = int(stats[label, cv2.CC_STAT_TOP])
            width = int(stats[label, cv2.CC_STAT_WIDTH])
            height = int(stats[label, cv2.CC_STAT_HEIGHT])
            centroid_x = float(centroids[label][0])
            centroid_y = float(centroids[label][1])
            component_mask = (labels == label).astype(np.uint8)
            instances.append({
                'centroid_x': centroid_x,
                'centroid_y': centroid_y,
                'area': area,
                'bbox': (left, top, width, height),
                'mask': component_mask,
            })

        instances.sort(key=lambda item: item['area'], reverse=True)
        return instances

    @staticmethod
    def _centroid_to_point(centroid, stamp, frame_id: str) -> PointStamped:
        msg = PointStamped()
        msg.header.stamp = stamp
        msg.header.frame_id = frame_id
        msg.point.x = float(centroid['centroid_x'])
        msg.point.y = float(centroid['centroid_y'])
        msg.point.z = float(centroid['area'])
        return msg

    @staticmethod
    def _centroids_to_pose_array(centroids, stamp, frame_id: str) -> PoseArray:
        msg = PoseArray()
        msg.header.stamp = stamp
        msg.header.frame_id = frame_id
        for index, centroid in enumerate(centroids):
            pose = Pose()
            pose.position.x = float(centroid['centroid_x'])
            pose.position.y = float(centroid['centroid_y'])
            pose.position.z = float(centroid['area'])
            pose.orientation.w = 1.0
            pose.orientation.z = float(index)
            msg.poses.append(pose)
        return msg

    @staticmethod
    def _draw_person_instances(overlay: np.ndarray, person_instances) -> np.ndarray:
        if not person_instances:
            return overlay

        output = overlay.copy()
        palette = [
            (0, 255, 0),
            (0, 200, 255),
            (255, 180, 0),
            (255, 80, 80),
            (180, 80, 255),
            (80, 255, 180),
        ]
        for index, instance in enumerate(person_instances, start=1):
            color = palette[(index - 1) % len(palette)]
            component_mask = (instance['mask'] * 255).astype(np.uint8)
            contours, _ = cv2.findContours(component_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(output, contours, -1, color, 2)
            left, top, width, height = instance['bbox']
            center = (int(round(instance['centroid_x'])), int(round(instance['centroid_y'])))
            cv2.drawMarker(output, center, color, markerType=cv2.MARKER_CROSS, markerSize=18, thickness=2)
            cv2.putText(
                output,
                f'P{index} a={instance["area"]}',
                (left, max(18, top - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                color,
                2,
                cv2.LINE_AA,
            )
            cv2.rectangle(output, (left, top), (left + width, top + height), color, 1)
        return output

    def _build_gpu_memory_message(self) -> str:
        if self._device is None or self._device.type != 'cuda' or not torch.cuda.is_available():
            return ''

        try:
            allocated_mb = torch.cuda.memory_allocated(self._device) / (1024.0 * 1024.0)
            reserved_mb = torch.cuda.memory_reserved(self._device) / (1024.0 * 1024.0)
            return ' | cuda_mem={:.0f}/{:.0f} MB'.format(allocated_mb, reserved_mb)
        except Exception:
            return ''

    def _build_gpu_load_message(self) -> str:
        if self._gpu_util_percent is None:
            return ''
        if self._gpu_freq_percent is None:
            return ' | gpu_load={:.0f}%'.format(self._gpu_util_percent)
        return ' | gpu_load={:.0f}% | gpu_freq={:.0f}%'.format(self._gpu_util_percent, self._gpu_freq_percent)

    @staticmethod
    def _image_msg_to_numpy(msg: Image):
        if msg.encoding not in ('rgb8', 'bgr8', 'mono8'):
            raise ValueError(f'Encoding no soportado: {msg.encoding}')

        channels = 1 if msg.encoding == 'mono8' else 3
        row_width = int(msg.step)
        flat = np.frombuffer(msg.data, dtype=np.uint8)
        rows = flat.reshape((int(msg.height), row_width))

        if channels == 1:
            image = rows[:, : int(msg.width)].copy()
        else:
            image = rows[:, : int(msg.width) * channels].reshape((int(msg.height), int(msg.width), channels)).copy()
            if msg.encoding == 'bgr8':
                image = image[..., ::-1].copy()
        return image

    @staticmethod
    def _numpy_to_image(array, encoding: str, stamp, frame_id: str) -> Image:
        msg = Image()
        msg.header.stamp = stamp
        msg.header.frame_id = frame_id
        msg.height = int(array.shape[0])
        msg.width = int(array.shape[1])
        msg.encoding = encoding
        msg.is_bigendian = False
        channels = 1 if array.ndim == 2 else int(array.shape[2])
        msg.step = int(array.shape[1] * channels * array.dtype.itemsize)
        msg.data = array.tobytes()
        return msg


def main(args=None) -> None:
    rclpy.init(args=args)
    node = TopicInferenceNode()
    rclpy.spin(node)


if __name__ == '__main__':
    main()