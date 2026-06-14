from __future__ import annotations

import time
from collections import deque
from pathlib import Path
from typing import Deque

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

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
from .rosbag_utils import build_stereo_calibration, load_rosbag_image_pairs, rectify_stereo_pair


class BagInferenceNode(Node):
    def __init__(self) -> None:
        super().__init__('cpgfanet_bag_inference')

        self.declare_parameter('repo_root', str(default_repo_root()))
        self.declare_parameter('checkpoint_path', '')
        self.declare_parameter('model_module', 'model.CrissCrossAttention_dual_2_sinINF')
        self.declare_parameter('model_class', 'FEANet')
        self.declare_parameter('bag_path', '')
        self.declare_parameter('rgb_topic', '/fanet/input/rgb')
        self.declare_parameter('thermal_topic', '/fanet/input/thermal')
        self.declare_parameter('output_dir', '/tmp/cpgfanet_bag_outputs')
        self.declare_parameter('device', 'cuda')
        self.declare_parameter('input_width', 640)
        self.declare_parameter('input_height', 360)
        self.declare_parameter('num_classes', 12)
        self.declare_parameter('rgb_scale', 255.0)
        self.declare_parameter('thermal_scale', 255.0)
        self.declare_parameter('overlay_alpha', 0.45)
        self.declare_parameter('max_pairs', 0)
        self.declare_parameter('sample_stride', 1)
        self.declare_parameter('pair_tolerance_ms', 50.0)
        self.declare_parameter('save_outputs', True)
        self.declare_parameter('save_alignment_outputs', True)
        self.declare_parameter('save_input_images', True)
        self.declare_parameter('enable_alignment_check', True)
        self.declare_parameter('infer_on_aligned_images', False)
        self.declare_parameter('alignment_overlay_alpha', 0.35)
        self.declare_parameter('rectify_alpha', 0.0)
        self.declare_parameter('display_results', True)
        self.declare_parameter('display_wait_ms', 1)
        self.declare_parameter('step_through_images', False)
        self.declare_parameter('display_dashboard', True)
        self.declare_parameter('display_dashboard_window_name', 'FANet aligned dashboard')
        self.declare_parameter('display_separate_windows', False)
        self.declare_parameter('display_rgb_input_window_name', 'FANet input RGB aligned')
        self.declare_parameter('display_thermal_input_window_name', 'FANet input thermal aligned')
        self.declare_parameter('display_overlay_window_name', 'FANet overlay aligned')
        self.declare_parameter('display_mask_window_name', 'FANet segmentation aligned')
        self.declare_parameter('draw_person_centroids', True)
        self.declare_parameter('person_class_index', 2)
        self.declare_parameter('person_min_pixels', 25)
        self.declare_parameter('person_min_bbox_width', 8)
        self.declare_parameter('person_min_bbox_height', 16)
        self.declare_parameter('person_morph_open_kernel', 1)
        self.declare_parameter('person_morph_close_kernel', 3)
        self.declare_parameter('enable_perf_logging', True)
        self.declare_parameter('perf_log_period_s', 5.0)
        self.declare_parameter('perf_window', 50)
        self.declare_parameter('enable_amp', False)
        self.declare_parameter('enable_cudnn_benchmark', True)
        self.declare_parameter('enable_cuda_sync_timing', False)
        self.declare_parameter(
            'rgb_camera_matrix',
            [
                894.7163072465, 0.0, 341.2116800525,
                0.0, 905.1990239793, 171.9461068409,
                0.0, 0.0, 1.0,
            ],
        )
        self.declare_parameter('rgb_distortion', [0.1801051399, -5.4233096945, 0.0, 0.0, 0.0])
        self.declare_parameter(
            'thermal_camera_matrix',
            [
                276.3844298115, 0.0, 314.9498359235,
                0.0, 268.8229935681, 189.2374843848,
                0.0, 0.0, 1.0,
            ],
        )
        self.declare_parameter('thermal_distortion', [-0.5877579533, 13.9448575456, 0.0, 0.0, 0.0])
        self.declare_parameter(
            'thermal_to_rgb_rotation',
            [
                0.9968084661, 0.0017959423, 0.0798101278,
                0.0078702669, 0.9926656953, -0.1206353026,
                -0.0794414301, 0.1208784180, 0.9894834346,
            ],
        )
        self.declare_parameter('thermal_to_rgb_translation_m', [-0.0234150327, 0.0488933772, -0.0078611506])

        self.mask_pub = self.create_publisher(Image, 'segmentation/mask_indices', 10)
        self.color_pub = self.create_publisher(Image, 'segmentation/mask_color', 10)
        self.overlay_pub = self.create_publisher(Image, 'segmentation/overlay', 10)
        self.alignment_pub = self.create_publisher(Image, 'alignment/thermal_on_rgb', 10)

        self._finished = False
        self._last_perf_log = time.perf_counter()
        self._run_count = 0
        self._enable_cuda_sync_timing = bool(self.get_parameter('enable_cuda_sync_timing').value)
        self._enable_amp = False
        self._device = None
        self._display_initialized = False

        perf_window = max(2, int(self.get_parameter('perf_window').value))
        self._load_times_ms: Deque[float] = deque(maxlen=perf_window)
        self._preprocess_times_ms: Deque[float] = deque(maxlen=perf_window)
        self._inference_times_ms: Deque[float] = deque(maxlen=perf_window)
        self._postprocess_times_ms: Deque[float] = deque(maxlen=perf_window)
        self._total_times_ms: Deque[float] = deque(maxlen=perf_window)

        self._timer = self.create_timer(0.1, self._run)

    def _sync_device(self) -> None:
        if not self._enable_cuda_sync_timing:
            return
        if self._device is not None and self._device.type == 'cuda' and torch.cuda.is_available():
            torch.cuda.synchronize(self._device)

    @staticmethod
    def _avg_ms(samples: Deque[float]) -> float:
        if not samples:
            return 0.0
        return float(sum(samples) / len(samples))

    def _maybe_log_performance(self) -> None:
        if not bool(self.get_parameter('enable_perf_logging').value):
            return
        if not self._total_times_ms:
            return

        now = time.perf_counter()
        if (now - self._last_perf_log) < max(0.5, float(self.get_parameter('perf_log_period_s').value)):
            return

        avg_total_ms = self._avg_ms(self._total_times_ms)
        avg_load_ms = self._avg_ms(self._load_times_ms)
        avg_pre_ms = self._avg_ms(self._preprocess_times_ms)
        avg_inf_ms = self._avg_ms(self._inference_times_ms)
        avg_post_ms = self._avg_ms(self._postprocess_times_ms)
        fps = 1000.0 / avg_total_ms if avg_total_ms > 1e-6 else 0.0
        self.get_logger().info(
            'Rosbag FANet | total={:.1f} ms | load={:.1f} ms | preprocess={:.1f} ms | infer={:.1f} ms | post={:.1f} ms | fps={:.2f} | runs={} | window={}'.format(
                avg_total_ms,
                avg_load_ms,
                avg_pre_ms,
                avg_inf_ms,
                avg_post_ms,
                fps,
                self._run_count,
                len(self._total_times_ms),
            )
        )
        self._last_perf_log = now

    def _record_run_stats(self, load_ms: float, preprocess_ms: float, inference_ms: float, postprocess_ms: float, total_ms: float) -> None:
        self._run_count += 1
        self._load_times_ms.append(load_ms)
        self._preprocess_times_ms.append(preprocess_ms)
        self._inference_times_ms.append(inference_ms)
        self._postprocess_times_ms.append(postprocess_ms)
        self._total_times_ms.append(total_ms)
        self._maybe_log_performance()

    def _run(self) -> None:
        if self._finished:
            return

        try:
            repo_root = Path(str(self.get_parameter('repo_root').value))
            checkpoint_path = Path(str(self.get_parameter('checkpoint_path').value))
            bag_path = Path(str(self.get_parameter('bag_path').value))
            output_dir = Path(str(self.get_parameter('output_dir').value))
            image_size = (
                int(self.get_parameter('input_width').value),
                int(self.get_parameter('input_height').value),
            )
            device_name = str(self.get_parameter('device').value)
            if device_name == 'cuda':
                device_name = 'cuda:0'

            if not checkpoint_path.is_file():
                raise FileNotFoundError(f'Checkpoint no encontrado: {checkpoint_path}')
            if not str(self.get_parameter('bag_path').value).strip():
                raise ValueError('Debes indicar bag_path con la carpeta del rosbag2 o uno de sus ficheros.')

            if device_name.startswith('cuda') and not torch.cuda.is_available():
                self.get_logger().warning('CUDA no está disponible. Cambio automático a CPU.')
                device_name = 'cpu'

            configure_torch_runtime(bool(self.get_parameter('enable_cudnn_benchmark').value))
            self._device = torch.device(device_name)
            self._enable_amp = bool(self.get_parameter('enable_amp').value) and self._device.type == 'cuda'
            self.get_logger().info(f'Inferencia FANet usando dispositivo: {self._device}')

            load_start = time.perf_counter()
            model = load_model(
                repo_root=repo_root,
                checkpoint_path=checkpoint_path,
                model_module=str(self.get_parameter('model_module').value),
                model_class=str(self.get_parameter('model_class').value),
                num_classes=int(self.get_parameter('num_classes').value),
                device=self._device,
            )
            bag_pairs = load_rosbag_image_pairs(
                bag_path=bag_path,
                rgb_topic=str(self.get_parameter('rgb_topic').value),
                thermal_topic=str(self.get_parameter('thermal_topic').value),
                pair_tolerance_ms=float(self.get_parameter('pair_tolerance_ms').value),
                sample_stride=max(1, int(self.get_parameter('sample_stride').value)),
                max_pairs=max(0, int(self.get_parameter('max_pairs').value)),
            )
            load_end = time.perf_counter()

            if not bag_pairs:
                raise FileNotFoundError('No se han podido emparejar imágenes RGB+térmica dentro del bag con la tolerancia indicada.')

            calibration = None
            if bool(self.get_parameter('enable_alignment_check').value):
                calibration = build_stereo_calibration(
                    rgb_camera_matrix=self.get_parameter('rgb_camera_matrix').value,
                    rgb_distortion=self.get_parameter('rgb_distortion').value,
                    thermal_camera_matrix=self.get_parameter('thermal_camera_matrix').value,
                    thermal_distortion=self.get_parameter('thermal_distortion').value,
                    thermal_to_rgb_rotation=self.get_parameter('thermal_to_rgb_rotation').value,
                    thermal_to_rgb_translation_m=self.get_parameter('thermal_to_rgb_translation_m').value,
                )

            self.get_logger().info(
                f'Procesando {len(bag_pairs)} pares del bag {bag_path} con topics {self.get_parameter("rgb_topic").value} y {self.get_parameter("thermal_topic").value}'
            )

            total_pairs = len(bag_pairs)
            for pair_index, pair in enumerate(bag_pairs, start=1):
                total_start = time.perf_counter()

                rgb_source = pair.rgb_image
                thermal_source = pair.thermal_image
                alignment_preview = None
                if calibration is not None:
                    rectified_rgb, rectified_thermal, rectified_thermal_color = rectify_stereo_pair(
                        rgb_image=pair.rgb_image,
                        thermal_image=pair.thermal_image,
                        calibration=calibration,
                        alpha=float(self.get_parameter('rectify_alpha').value),
                    )
                    alignment_preview = blend_overlay(
                        rgb_image=rectified_rgb,
                        color_mask=rectified_thermal_color,
                        alpha=float(self.get_parameter('alignment_overlay_alpha').value),
                    )
                    if bool(self.get_parameter('infer_on_aligned_images').value):
                        rgb_source = rectified_rgb
                        thermal_source = rectified_thermal

                pair_output_dir = output_dir / pair.name
                if alignment_preview is not None and bool(self.get_parameter('save_alignment_outputs').value):
                    save_outputs(
                        output_dir=pair_output_dir / 'alignment',
                        mask=thermal_source,
                        color_mask=np.repeat(thermal_source[..., None], 3, axis=2),
                        overlay=alignment_preview,
                    )
                    self.alignment_pub.publish(self._numpy_to_image(alignment_preview, 'rgb8'))

                preprocess_start = time.perf_counter()
                input_tensor, rgb_resized, thermal_resized = preprocess_pair(
                    rgb_image=rgb_source,
                    thermal_image=thermal_source,
                    image_size=image_size,
                    rgb_scale=float(self.get_parameter('rgb_scale').value),
                    thermal_scale=float(self.get_parameter('thermal_scale').value),
                )
                preprocess_end = time.perf_counter()

                self._sync_device()
                inference_start = time.perf_counter()
                mask = predict_mask(
                    model=model,
                    input_tensor=input_tensor,
                    device=self._device,
                    use_amp=self._enable_amp,
                )
                if mask.shape != rgb_resized.shape[:2]:
                    mask = cv2.resize(
                        mask.astype(np.uint8),
                        (int(rgb_resized.shape[1]), int(rgb_resized.shape[0])),
                        interpolation=cv2.INTER_NEAREST,
                    )
                self._sync_device()
                inference_end = time.perf_counter()

                postprocess_start = time.perf_counter()
                color_mask = colorize_mask(mask)
                overlay_base = blend_overlay(
                    rgb_image=rgb_resized,
                    color_mask=color_mask,
                    alpha=float(self.get_parameter('overlay_alpha').value),
                )
                person_instances = self._extract_person_instances(mask)
                overlay = self._draw_person_instances(overlay_base, person_instances)
                mask_display = self._draw_person_instances(color_mask, person_instances)

                if bool(self.get_parameter('save_outputs').value):
                    save_outputs(output_dir=pair_output_dir, mask=mask, color_mask=mask_display, overlay=overlay)

                if bool(self.get_parameter('save_input_images').value):
                    save_outputs(
                        output_dir=pair_output_dir / 'inputs',
                        mask=thermal_resized,
                        color_mask=np.repeat(thermal_resized[..., None], 3, axis=2),
                        overlay=rgb_resized,
                    )

                self._display_images(
                    rgb_input=rgb_resized,
                    thermal_input=thermal_resized,
                    overlay=overlay,
                    mask_display=mask_display,
                    progress_text=f'par {pair_index}/{total_pairs} | {pair.name}',
                )

                self.mask_pub.publish(self._numpy_to_image(mask, 'mono8'))
                self.color_pub.publish(self._numpy_to_image(mask_display, 'rgb8'))
                self.overlay_pub.publish(self._numpy_to_image(overlay, 'rgb8'))
                postprocess_end = time.perf_counter()

                load_ms = (load_end - load_start) * 1000.0 if self._run_count == 0 else 0.0
                preprocess_ms = (preprocess_end - preprocess_start) * 1000.0
                inference_ms = (inference_end - inference_start) * 1000.0
                postprocess_ms = (postprocess_end - postprocess_start) * 1000.0
                total_ms = (postprocess_end - total_start) * 1000.0
                self._record_run_stats(load_ms, preprocess_ms, inference_ms, postprocess_ms, total_ms)

                self.get_logger().info(
                    f'Bag FANet completado | par={pair.name} | total={total_ms:.2f} ms | preprocess={preprocess_ms:.2f} ms | infer={inference_ms:.2f} ms | post={postprocess_ms:.2f} ms'
                )

            self.get_logger().info(f'Resultados guardados en: {output_dir}')
            self._finished = True
            self.destroy_node()
            rclpy.shutdown()
        except Exception as exc:
            self.get_logger().error(str(exc))
            self._finished = True
            self._cleanup_display()
            self.destroy_node()
            rclpy.shutdown()

    def _display_images(
        self,
        rgb_input: np.ndarray,
        thermal_input: np.ndarray,
        overlay: np.ndarray,
        mask_display: np.ndarray,
        progress_text: str,
    ) -> None:
        if not bool(self.get_parameter('display_results').value):
            return

        if not self._display_initialized:
            dashboard_window = str(self.get_parameter('display_dashboard_window_name').value)
            rgb_window = str(self.get_parameter('display_rgb_input_window_name').value)
            thermal_window = str(self.get_parameter('display_thermal_input_window_name').value)
            overlay_window = str(self.get_parameter('display_overlay_window_name').value)
            mask_window = str(self.get_parameter('display_mask_window_name').value)

            if bool(self.get_parameter('display_dashboard').value):
                cv2.namedWindow(dashboard_window, cv2.WINDOW_NORMAL)
                cv2.resizeWindow(dashboard_window, 1400, 900)
                cv2.moveWindow(dashboard_window, 20, 20)

            if bool(self.get_parameter('display_separate_windows').value):
                cv2.namedWindow(rgb_window, cv2.WINDOW_NORMAL)
                cv2.namedWindow(thermal_window, cv2.WINDOW_NORMAL)
                cv2.namedWindow(overlay_window, cv2.WINDOW_NORMAL)
                cv2.namedWindow(mask_window, cv2.WINDOW_NORMAL)

                cv2.resizeWindow(rgb_window, 640, 360)
                cv2.resizeWindow(thermal_window, 640, 360)
                cv2.resizeWindow(overlay_window, 640, 360)
                cv2.resizeWindow(mask_window, 640, 360)

                cv2.moveWindow(rgb_window, 20, 20)
                cv2.moveWindow(thermal_window, 700, 20)
                cv2.moveWindow(overlay_window, 20, 430)
                cv2.moveWindow(mask_window, 700, 430)
            self._display_initialized = True

        thermal_display = cv2.applyColorMap(thermal_input, cv2.COLORMAP_INFERNO)
        rgb_bgr = cv2.cvtColor(rgb_input, cv2.COLOR_RGB2BGR)
        overlay_bgr = cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR)
        mask_bgr = cv2.cvtColor(mask_display, cv2.COLOR_RGB2BGR)

        if bool(self.get_parameter('display_dashboard').value):
            dashboard = self._build_dashboard(
                rgb_bgr=rgb_bgr,
                thermal_bgr=thermal_display,
                overlay_bgr=overlay_bgr,
                mask_bgr=mask_bgr,
                progress_text=progress_text,
            )
            cv2.imshow(str(self.get_parameter('display_dashboard_window_name').value), dashboard)

        if bool(self.get_parameter('display_separate_windows').value):
            cv2.imshow(str(self.get_parameter('display_rgb_input_window_name').value), rgb_bgr)
            cv2.imshow(str(self.get_parameter('display_thermal_input_window_name').value), thermal_display)
            cv2.imshow(str(self.get_parameter('display_overlay_window_name').value), overlay_bgr)
            cv2.imshow(str(self.get_parameter('display_mask_window_name').value), mask_bgr)

        key = self._wait_for_display_input()
        if key in (27, ord('q')):
            raise KeyboardInterrupt('Visualización detenida por el usuario.')

    def _wait_for_display_input(self) -> int:
        if bool(self.get_parameter('step_through_images').value):
            while True:
                key = cv2.waitKey(50) & 0xFF
                if key in (27, ord('q'), ord(' '), ord('n'), 13):
                    return key
        return cv2.waitKey(max(1, int(self.get_parameter('display_wait_ms').value))) & 0xFF

    def _build_dashboard(
        self,
        rgb_bgr: np.ndarray,
        thermal_bgr: np.ndarray,
        overlay_bgr: np.ndarray,
        mask_bgr: np.ndarray,
        progress_text: str,
    ) -> np.ndarray:
        if bool(self.get_parameter('infer_on_aligned_images').value):
            rgb_title = 'RGB usada por el modelo (alineada)'
            thermal_title = 'Termica usada por el modelo (gris alineada)'
        else:
            rgb_title = 'RGB usada por el modelo (raw)'
            thermal_title = 'Termica usada por el modelo (gris raw)'

        top_left = self._annotate_panel(rgb_bgr, rgb_title)
        top_right = self._annotate_panel(thermal_bgr, thermal_title + ' | preview color')
        bottom_left = self._annotate_panel(overlay_bgr, 'Overlay alineado')
        bottom_right = self._annotate_panel(mask_bgr, 'Segmentacion alineada')
        top_row = np.hstack([top_left, top_right])
        bottom_row = np.hstack([bottom_left, bottom_right])
        dashboard = np.vstack([top_row, bottom_row])
        cv2.rectangle(dashboard, (0, dashboard.shape[0] - 36), (dashboard.shape[1], dashboard.shape[0]), (24, 24, 24), thickness=-1)
        cv2.putText(dashboard, progress_text, (12, dashboard.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        return dashboard

    @staticmethod
    def _annotate_panel(image: np.ndarray, title: str) -> np.ndarray:
        panel = image.copy()
        cv2.rectangle(panel, (0, 0), (panel.shape[1], 30), (32, 32, 32), thickness=-1)
        cv2.putText(panel, title, (12, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)
        return panel

    def _cleanup_display(self) -> None:
        if self._display_initialized:
            cv2.destroyAllWindows()
            self._display_initialized = False

    def _extract_person_instances(self, mask: np.ndarray):
        person_class_index = int(self.get_parameter('person_class_index').value)
        min_pixels = max(1, int(self.get_parameter('person_min_pixels').value))
        min_bbox_width = max(1, int(self.get_parameter('person_min_bbox_width').value))
        min_bbox_height = max(1, int(self.get_parameter('person_min_bbox_height').value))
        binary = (mask == person_class_index).astype(np.uint8)
        if not np.any(binary):
            return []

        open_kernel_size = max(0, int(self.get_parameter('person_morph_open_kernel').value))
        close_kernel_size = max(0, int(self.get_parameter('person_morph_close_kernel').value))
        if open_kernel_size > 1:
            open_kernel = np.ones((open_kernel_size, open_kernel_size), dtype=np.uint8)
            binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, open_kernel)
        if close_kernel_size > 1:
            close_kernel = np.ones((close_kernel_size, close_kernel_size), dtype=np.uint8)
            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, close_kernel)
        if not np.any(binary):
            return []

        component_count, _labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
        instances = []
        for label in range(1, component_count):
            area = int(stats[label, cv2.CC_STAT_AREA])
            if area < min_pixels:
                continue
            left = int(stats[label, cv2.CC_STAT_LEFT])
            top = int(stats[label, cv2.CC_STAT_TOP])
            width = int(stats[label, cv2.CC_STAT_WIDTH])
            height = int(stats[label, cv2.CC_STAT_HEIGHT])
            if width < min_bbox_width or height < min_bbox_height:
                continue
            instances.append(
                {
                    'centroid_x': float(centroids[label][0]),
                    'centroid_y': float(centroids[label][1]),
                    'area': area,
                    'bbox': (left, top, width, height),
                }
            )
        instances.sort(key=lambda item: int(item['area']), reverse=True)
        return instances

    def _draw_person_instances(self, image: np.ndarray, person_instances) -> np.ndarray:
        if not bool(self.get_parameter('draw_person_centroids').value) or not person_instances:
            return image

        output = image.copy()
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
            center = (int(round(instance['centroid_x'])), int(round(instance['centroid_y'])))
            cv2.drawMarker(output, center, color, markerType=cv2.MARKER_CROSS, markerSize=20, thickness=2)
            left, top, width, height = instance['bbox']
            cv2.rectangle(output, (left, top), (left + width, top + height), color, 2)
        return output

    def _numpy_to_image(self, array, encoding: str) -> Image:
        msg = Image()
        msg.header.stamp = self.get_clock().now().to_msg()
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
    node = BagInferenceNode()
    try:
        rclpy.spin(node)
    finally:
        node._cleanup_display()


if __name__ == '__main__':
    main()