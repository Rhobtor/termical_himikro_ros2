from __future__ import annotations

import time
from collections import deque
from pathlib import Path
from typing import Deque, List, Optional, Tuple

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

import torch

from .model_runtime import (
    blend_overlay,
    colorize_mask,
    configure_torch_runtime,
    default_repo_root,
    load_and_preprocess,
    load_image_pair,
    load_model,
    predict_mask,
    preprocess_pair,
    save_outputs,
)


class OfflineInferenceNode(Node):
    def __init__(self) -> None:
        super().__init__('cpgfanet_offline_inference')

        self.declare_parameter('repo_root', str(default_repo_root()))
        self.declare_parameter('checkpoint_path', '')
        self.declare_parameter('model_module', 'model.FEANet')
        self.declare_parameter('model_class', 'FEANet')
        self.declare_parameter('rgb_image_path', '')
        self.declare_parameter('thermal_image_path', '')
        self.declare_parameter('rgb_image_dir', '')
        self.declare_parameter('thermal_image_dir', '')
        self.declare_parameter('output_dir', '/tmp/cpgfanet_outputs')
        self.declare_parameter('device', 'cuda')
        self.declare_parameter('input_width', 640)
        self.declare_parameter('input_height', 480)
        self.declare_parameter('num_classes', 9)
        self.declare_parameter('rgb_scale', 255.0)
        self.declare_parameter('thermal_scale', 255.0)
        self.declare_parameter('overlay_alpha', 0.45)
        self.declare_parameter('run_once', True)
        self.declare_parameter('loop_hz', 10.0)
        self.declare_parameter('loop_dataset', False)
        self.declare_parameter('max_images', 0)
        self.declare_parameter('save_outputs', True)
        self.declare_parameter('display_results', False)
        self.declare_parameter('display_wait_ms', 1)
        self.declare_parameter('display_window_name', 'CPGFANet overlay')
        self.declare_parameter('enable_perf_logging', True)
        self.declare_parameter('perf_log_period_s', 5.0)
        self.declare_parameter('perf_window', 50)
        self.declare_parameter('perf_warmup_runs', 3)
        self.declare_parameter('preload_images', True)
        self.declare_parameter('preprocess_on_load', False)
        self.declare_parameter('enable_amp', False)
        self.declare_parameter('enable_cudnn_benchmark', True)
        self.declare_parameter('enable_cuda_sync_timing', False)

        self.mask_pub = self.create_publisher(Image, 'segmentation/mask_indices', 10)
        self.color_pub = self.create_publisher(Image, 'segmentation/mask_color', 10)
        self.overlay_pub = self.create_publisher(Image, 'segmentation/overlay', 10)

        self._finished = False
        self._runtime_ready = False
        self._model = None
        self._repo_root = None
        self._checkpoint_path = None
        self._rgb_path = None
        self._thermal_path = None
        self._rgb_dir = None
        self._thermal_dir = None
        self._output_dir = None
        self._device = None
        self._image_size = None
        self._overlay_alpha = 0.45
        self._image_jobs = []
        self._sample_cache = []
        self._job_index = 0
        self._display_enabled = False
        self._display_window_name = 'CPGFANet overlay'
        self._cv2 = None
        self._run_count = 0
        self._last_perf_log = time.perf_counter()
        self._enable_amp = False
        self._enable_cuda_sync_timing = bool(self.get_parameter('enable_cuda_sync_timing').value)

        perf_window = max(2, int(self.get_parameter('perf_window').value))
        self._load_times_ms = deque(maxlen=perf_window)
        self._preprocess_times_ms = deque(maxlen=perf_window)
        self._inference_times_ms = deque(maxlen=perf_window)
        self._postprocess_times_ms = deque(maxlen=perf_window)
        self._total_times_ms = deque(maxlen=perf_window)

        loop_hz = max(0.1, float(self.get_parameter('loop_hz').value))
        self._timer = self.create_timer(1.0 / loop_hz, self._run_once)

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
            'Rendimiento FANet | total={:.1f} ms | load={:.1f} ms | preprocess={:.1f} ms | infer={:.1f} ms | post={:.1f} ms | fps={:.2f} | runs={} | window={}'.format(
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

    def _record_run_stats(
        self,
        load_ms: float,
        preprocess_ms: float,
        inference_ms: float,
        postprocess_ms: float,
        total_ms: float,
    ) -> None:
        self._run_count += 1
        if self._run_count <= max(0, int(self.get_parameter('perf_warmup_runs').value)):
            return

        self._load_times_ms.append(load_ms)
        self._preprocess_times_ms.append(preprocess_ms)
        self._inference_times_ms.append(inference_ms)
        self._postprocess_times_ms.append(postprocess_ms)
        self._total_times_ms.append(total_ms)
        self._maybe_log_performance()

    def _ensure_runtime_ready(self) -> None:
        if self._runtime_ready:
            return

        self._repo_root = Path(self.get_parameter('repo_root').value)
        self._checkpoint_path = Path(self.get_parameter('checkpoint_path').value)
        self._rgb_path = Path(self.get_parameter('rgb_image_path').value)
        self._thermal_path = Path(self.get_parameter('thermal_image_path').value)
        self._rgb_dir = Path(self.get_parameter('rgb_image_dir').value) if self.get_parameter('rgb_image_dir').value else None
        self._thermal_dir = Path(self.get_parameter('thermal_image_dir').value) if self.get_parameter('thermal_image_dir').value else None
        self._output_dir = Path(self.get_parameter('output_dir').value)
        self._image_size = (
            int(self.get_parameter('input_width').value),
            int(self.get_parameter('input_height').value),
        )
        device_name = self.get_parameter('device').value
        if device_name == 'cuda':
            device_name = 'cuda:0'

        if not self._checkpoint_path.is_file():
            raise FileNotFoundError(f'Checkpoint no encontrado: {self._checkpoint_path}')
        self._image_jobs = self._build_image_jobs()
        if not self._image_jobs:
            raise FileNotFoundError('No se encontraron pares RGB/TIR para inferencia offline.')

        if device_name.startswith('cuda') and not torch.cuda.is_available():
            self.get_logger().warning('CUDA no está disponible. Cambio automático a CPU.')
            device_name = 'cpu'

        configure_torch_runtime(bool(self.get_parameter('enable_cudnn_benchmark').value))

        self._device = torch.device(device_name)
        self._overlay_alpha = float(self.get_parameter('overlay_alpha').value)
        self._display_enabled = bool(self.get_parameter('display_results').value)
        self._display_window_name = str(self.get_parameter('display_window_name').value)
        self._enable_amp = bool(self.get_parameter('enable_amp').value) and self._device.type == 'cuda'

        self._model = load_model(
            repo_root=self._repo_root,
            checkpoint_path=self._checkpoint_path,
            model_module=self.get_parameter('model_module').value,
            model_class=self.get_parameter('model_class').value,
            num_classes=int(self.get_parameter('num_classes').value),
            device=self._device,
        )

        self._sample_cache = self._build_sample_cache()

        self.get_logger().info(
            f'Modelo cargado en {self._device.type}: {self._checkpoint_path}'
        )
        self.get_logger().info(
            f'Pares RGB/TIR listos para procesar: {len(self._image_jobs)}'
        )
        self._runtime_ready = True

    def _build_sample_cache(self) -> List[Optional[dict]]:
        preload_images = bool(self.get_parameter('preload_images').value)
        preprocess_on_load = bool(self.get_parameter('preprocess_on_load').value)
        if not preload_images and not preprocess_on_load:
            return [None] * len(self._image_jobs)

        cached_samples = []
        for rgb_path, thermal_path, _ in self._image_jobs:
            if preprocess_on_load:
                input_tensor, rgb_resized = load_and_preprocess(
                    rgb_path=rgb_path,
                    thermal_path=thermal_path,
                    image_size=self._image_size,
                    rgb_scale=float(self.get_parameter('rgb_scale').value),
                    thermal_scale=float(self.get_parameter('thermal_scale').value),
                )
                cached_samples.append(
                    {
                        'input_tensor': input_tensor,
                        'rgb_resized': rgb_resized,
                    }
                )
                continue

            rgb_image, thermal_image = load_image_pair(
                rgb_path=rgb_path,
                thermal_path=thermal_path,
                image_size=self._image_size,
            )
            cached_samples.append(
                {
                    'rgb_image': rgb_image,
                    'thermal_image': thermal_image,
                }
            )
        return cached_samples

    def _build_image_jobs(self) -> List[Tuple[Path, Path, str]]:
        if self._rgb_dir or self._thermal_dir:
            if not self._rgb_dir or not self._thermal_dir:
                raise ValueError('Debes indicar ambos parámetros: rgb_image_dir y thermal_image_dir.')
            if not self._rgb_dir.is_dir():
                raise FileNotFoundError(f'Directorio RGB no encontrado: {self._rgb_dir}')
            if not self._thermal_dir.is_dir():
                raise FileNotFoundError(f'Directorio térmico no encontrado: {self._thermal_dir}')
            jobs = self._collect_directory_pairs(self._rgb_dir, self._thermal_dir)
        else:
            if not self._rgb_path.is_file():
                raise FileNotFoundError(f'Imagen RGB no encontrada: {self._rgb_path}')
            if not self._thermal_path.is_file():
                raise FileNotFoundError(f'Imagen térmica no encontrada: {self._thermal_path}')
            jobs = [(self._rgb_path, self._thermal_path, self._rgb_path.stem)]

        max_images = max(0, int(self.get_parameter('max_images').value))
        if max_images > 0:
            jobs = jobs[:max_images]
        return jobs

    @staticmethod
    def _collect_directory_pairs(rgb_dir: Path, thermal_dir: Path) -> List[Tuple[Path, Path, str]]:
        valid_suffixes = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'}

        rgb_files = {
            path.stem: path
            for path in sorted(rgb_dir.iterdir())
            if path.is_file() and path.suffix.lower() in valid_suffixes
        }
        thermal_files = {
            path.stem: path
            for path in sorted(thermal_dir.iterdir())
            if path.is_file() and path.suffix.lower() in valid_suffixes
        }

        common_names = sorted(set(rgb_files) & set(thermal_files))
        return [(rgb_files[name], thermal_files[name], name) for name in common_names]

    def _get_current_job(self) -> Tuple[Path, Path, str]:
        if not self._image_jobs:
            raise RuntimeError('No hay pares cargados para inferencia.')
        if self._job_index >= len(self._image_jobs):
            if bool(self.get_parameter('loop_dataset').value):
                self._job_index = 0
            else:
                raise StopIteration
        return self._image_jobs[self._job_index]

    def _advance_job_index(self) -> None:
        if len(self._image_jobs) > 1:
            self._job_index += 1

    def _display_overlay(self, overlay, job_name: str) -> None:
        if not self._display_enabled:
            return
        if self._cv2 is None:
            try:
                import cv2
            except ImportError as exc:
                raise RuntimeError(
                    'display_results=true requiere OpenCV. Instala python3-opencv dentro del entorno/contenedor.'
                ) from exc
            self._cv2 = cv2

        bgr_overlay = self._cv2.cvtColor(overlay, self._cv2.COLOR_RGB2BGR)
        self._cv2.imshow(self._display_window_name, bgr_overlay)
        if hasattr(self._cv2, 'setWindowTitle'):
            self._cv2.setWindowTitle(self._display_window_name, f'{self._display_window_name} | {job_name}')
        wait_ms = max(0, int(self.get_parameter('display_wait_ms').value))
        key = self._cv2.waitKey(wait_ms) & 0xFF
        if key in (27, ord('q')):
            raise KeyboardInterrupt('Visualización detenida por el usuario.')

    def _cleanup_display(self) -> None:
        if self._cv2 is not None:
            self._cv2.destroyAllWindows()

    def _run_once(self) -> None:
        if self._finished:
            return

        try:
            total_start = time.perf_counter()
            self._ensure_runtime_ready()

            load_start = time.perf_counter()
            rgb_path, thermal_path, job_name = self._get_current_job()
            cached_sample = self._sample_cache[self._job_index] if self._sample_cache else None
            load_end = time.perf_counter()

            preprocess_start = time.perf_counter()
            if cached_sample is None:
                input_tensor, rgb_resized = load_and_preprocess(
                    rgb_path=rgb_path,
                    thermal_path=thermal_path,
                    image_size=self._image_size,
                    rgb_scale=float(self.get_parameter('rgb_scale').value),
                    thermal_scale=float(self.get_parameter('thermal_scale').value),
                )
            elif 'input_tensor' in cached_sample:
                input_tensor = cached_sample['input_tensor']
                rgb_resized = cached_sample['rgb_resized']
            else:
                input_tensor, rgb_resized, _ = preprocess_pair(
                    rgb_image=cached_sample['rgb_image'],
                    thermal_image=cached_sample['thermal_image'],
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
            color_mask = colorize_mask(mask)
            overlay = blend_overlay(
                rgb_image=rgb_resized,
                color_mask=color_mask,
                alpha=self._overlay_alpha,
            )

            if bool(self.get_parameter('save_outputs').value):
                save_dir = self._output_dir if len(self._image_jobs) == 1 else self._output_dir / job_name
                save_outputs(output_dir=save_dir, mask=mask, color_mask=color_mask, overlay=overlay)
            self._publish_images(mask=mask, color_mask=color_mask, overlay=overlay)
            self._display_overlay(overlay=overlay, job_name=job_name)
            postprocess_end = time.perf_counter()

            load_ms = (load_end - load_start) * 1000.0
            preprocess_ms = (preprocess_end - preprocess_start) * 1000.0
            inference_ms = (inference_end - inference_start) * 1000.0
            postprocess_ms = (postprocess_end - postprocess_start) * 1000.0
            total_ms = (postprocess_end - total_start) * 1000.0

            self._record_run_stats(load_ms, preprocess_ms, inference_ms, postprocess_ms, total_ms)

            self.get_logger().info(
                f'Inferencia FANet completada | imagen={job_name} | total={total_ms:.2f} ms | preprocess={preprocess_ms:.2f} ms | infer={inference_ms:.2f} ms | post={postprocess_ms:.2f} ms'
            )
            if bool(self.get_parameter('save_outputs').value):
                self.get_logger().info(
                    f'Resultados guardados en: {self._output_dir if len(self._image_jobs) == 1 else self._output_dir / job_name}'
                )

            self._advance_job_index()

            if bool(self.get_parameter('run_once').value):
                self._finished = True
                self._cleanup_display()
                self.destroy_node()
                rclpy.shutdown()
        except StopIteration:
            self.get_logger().info('Dataset procesado por completo.')
            self._finished = True
            self._cleanup_display()
            self.destroy_node()
            rclpy.shutdown()
        except KeyboardInterrupt as exc:
            self.get_logger().info(str(exc))
            self._finished = True
            self._cleanup_display()
            self.destroy_node()
            rclpy.shutdown()
        except Exception as exc:
            self.get_logger().error(str(exc))
            self._finished = True
            self._cleanup_display()
            self.destroy_node()
            rclpy.shutdown()

    def _publish_images(self, mask, color_mask, overlay) -> None:
        stamp = self.get_clock().now().to_msg()
        self.mask_pub.publish(self._numpy_to_image(mask, 'mono8', stamp))
        self.color_pub.publish(self._numpy_to_image(color_mask, 'rgb8', stamp))
        self.overlay_pub.publish(self._numpy_to_image(overlay, 'rgb8', stamp))

    @staticmethod
    def _numpy_to_image(array, encoding: str, stamp) -> Image:
        msg = Image()
        msg.header.stamp = stamp
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
    node = OfflineInferenceNode()
    rclpy.spin(node)


if __name__ == '__main__':
    main()