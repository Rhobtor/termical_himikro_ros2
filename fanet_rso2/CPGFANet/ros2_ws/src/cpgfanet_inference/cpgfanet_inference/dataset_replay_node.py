from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional, Tuple

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

from .model_runtime import load_image_pair


class DatasetReplayNode(Node):
    def __init__(self) -> None:
        super().__init__('cpgfanet_dataset_replay')

        self.declare_parameter('rgb_image_path', '')
        self.declare_parameter('thermal_image_path', '')
        self.declare_parameter('rgb_image_dir', '')
        self.declare_parameter('thermal_image_dir', '')
        self.declare_parameter('input_width', 640)
        self.declare_parameter('input_height', 480)
        self.declare_parameter('target_fps', 20.0)
        self.declare_parameter('loop_dataset', True)
        self.declare_parameter('max_images', 0)
        self.declare_parameter('preload_images', True)
        self.declare_parameter('rgb_topic', 'fanet/input/rgb')
        self.declare_parameter('thermal_topic', 'fanet/input/thermal')
        self.declare_parameter('log_every_n_frames', 100)
        self.declare_parameter('perf_log_period_s', 2.0)

        self.rgb_pub = self.create_publisher(Image, str(self.get_parameter('rgb_topic').value), 1)
        self.thermal_pub = self.create_publisher(Image, str(self.get_parameter('thermal_topic').value), 1)

        self._image_size = (
            int(self.get_parameter('input_width').value),
            int(self.get_parameter('input_height').value),
        )
        self._jobs = []
        self._cache = []
        self._job_index = 0
        self._publish_count = 0
        self._publish_count_at_last_log = 0
        self._start_time = time.perf_counter()
        self._last_publish_time = self._start_time
        self._last_perf_log_time = self._start_time

        self._ensure_runtime_ready()

        target_fps = max(0.1, float(self.get_parameter('target_fps').value))
        self._timer = self.create_timer(1.0 / target_fps, self._publish_next)

    def _ensure_runtime_ready(self) -> None:
        self._jobs = self._build_image_jobs()
        if not self._jobs:
            raise FileNotFoundError('No se encontraron pares RGB/TIR para publicar por topico.')

        if bool(self.get_parameter('preload_images').value):
            self._cache = [
                load_image_pair(rgb_path=rgb_path, thermal_path=thermal_path, image_size=self._image_size)
                for rgb_path, thermal_path, _ in self._jobs
            ]
        else:
            self._cache = [None] * len(self._jobs)

        self.get_logger().info(f'Replay dataset listo con {len(self._jobs)} pares RGB/TIR.')

    def _build_image_jobs(self) -> List[Tuple[Path, Path, str]]:
        rgb_image_dir = str(self.get_parameter('rgb_image_dir').value)
        thermal_image_dir = str(self.get_parameter('thermal_image_dir').value)
        rgb_dir = Path(rgb_image_dir) if rgb_image_dir else None
        thermal_dir = Path(thermal_image_dir) if thermal_image_dir else None

        if rgb_dir or thermal_dir:
            if not rgb_dir or not thermal_dir:
                raise ValueError('Debes indicar ambos parametros: rgb_image_dir y thermal_image_dir.')
            if not rgb_dir.is_dir():
                raise FileNotFoundError(f'Directorio RGB no encontrado: {rgb_dir}')
            if not thermal_dir.is_dir():
                raise FileNotFoundError(f'Directorio termico no encontrado: {thermal_dir}')
            jobs = self._collect_directory_pairs(rgb_dir, thermal_dir)
        else:
            rgb_path = Path(str(self.get_parameter('rgb_image_path').value))
            thermal_path = Path(str(self.get_parameter('thermal_image_path').value))
            if not rgb_path.is_file():
                raise FileNotFoundError(f'Imagen RGB no encontrada: {rgb_path}')
            if not thermal_path.is_file():
                raise FileNotFoundError(f'Imagen termica no encontrada: {thermal_path}')
            jobs = [(rgb_path, thermal_path, rgb_path.stem)]

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

    def _publish_next(self) -> None:
        if self._job_index >= len(self._jobs):
            if bool(self.get_parameter('loop_dataset').value):
                self._job_index = 0
            else:
                self.get_logger().info('Replay dataset completado.')
                self.destroy_node()
                rclpy.shutdown()
                return

        rgb_path, thermal_path, job_name = self._jobs[self._job_index]
        cached_pair = self._cache[self._job_index]
        if cached_pair is None:
            rgb_image, thermal_image = load_image_pair(
                rgb_path=rgb_path,
                thermal_path=thermal_path,
                image_size=self._image_size,
            )
        else:
            rgb_image, thermal_image = cached_pair

        stamp = self.get_clock().now().to_msg()
        self.rgb_pub.publish(self._numpy_to_image(rgb_image, 'rgb8', stamp, job_name))
        self.thermal_pub.publish(self._numpy_to_image(thermal_image, 'mono8', stamp, job_name))

        self._publish_count += 1
        self._last_publish_time = time.perf_counter()
        self._maybe_log_performance(job_name)
        log_every_n = max(0, int(self.get_parameter('log_every_n_frames').value))
        if log_every_n > 0 and (self._publish_count % log_every_n) == 0:
            self.get_logger().info(
                f'Replay publicado: frames={self._publish_count} ultimo={job_name}'
            )

        self._job_index += 1

    def _maybe_log_performance(self, job_name: str) -> None:
        now = time.perf_counter()
        log_period = max(0.5, float(self.get_parameter('perf_log_period_s').value))
        if (now - self._last_perf_log_time) < log_period:
            return

        elapsed = max(now - self._last_perf_log_time, 1e-6)
        total_elapsed = max(now - self._start_time, 1e-6)
        published_since_last = self._publish_count - self._publish_count_at_last_log
        actual_fps = published_since_last / elapsed
        average_fps = self._publish_count / total_elapsed
        target_fps = float(self.get_parameter('target_fps').value)

        self.get_logger().info(
            'Replay FPS | target={:.2f} | actual={:.2f} | avg={:.2f} | frames={} | ultimo={}'.format(
                target_fps,
                actual_fps,
                average_fps,
                self._publish_count,
                job_name,
            )
        )

        self._publish_count_at_last_log = self._publish_count
        self._last_perf_log_time = now

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
    node = DatasetReplayNode()
    rclpy.spin(node)


if __name__ == '__main__':
    main()