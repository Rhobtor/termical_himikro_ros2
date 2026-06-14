from __future__ import annotations

import csv
from pathlib import Path

import cv2
import numpy as np
import rclpy
from rclpy.node import Node

from .rosbag_utils import ensure_grayscale, load_rosbag_image_pairs


class BagImageExtractorNode(Node):
    def __init__(self) -> None:
        super().__init__('cpgfanet_bag_image_extractor')

        self.declare_parameter('bag_path', '')
        self.declare_parameter('rgb_topic', '/fanet/raw/rgb')
        self.declare_parameter('thermal_topic', '/fanet/raw/thermal')
        self.declare_parameter('output_dir', '/tmp/cpgfanet_bag_extract')
        self.declare_parameter('pair_tolerance_ms', 50.0)
        self.declare_parameter('sample_stride', 1)
        self.declare_parameter('max_pairs', 0)
        self.declare_parameter('image_format', 'png')
        self.declare_parameter('save_rgb', True)
        self.declare_parameter('save_thermal_raw', True)
        self.declare_parameter('save_thermal_color', True)
        self.declare_parameter('log_every', 25)

        self._finished = False
        self._timer = self.create_timer(0.1, self._run)

    def _run(self) -> None:
        if self._finished:
            return

        try:
            bag_path_raw = str(self.get_parameter('bag_path').value).strip()
            if not bag_path_raw:
                raise ValueError('Debes indicar bag_path con la carpeta del rosbag2 o con la carpeta padre que contiene varios bags.')

            bag_path = Path(bag_path_raw)
            output_dir = Path(str(self.get_parameter('output_dir').value))
            image_format = str(self.get_parameter('image_format').value).strip().lower() or 'png'
            if image_format not in {'png', 'jpg', 'jpeg'}:
                raise ValueError(f'Formato de imagen no soportado: {image_format}')

            bag_pairs = load_rosbag_image_pairs(
                bag_path=bag_path,
                rgb_topic=str(self.get_parameter('rgb_topic').value),
                thermal_topic=str(self.get_parameter('thermal_topic').value),
                pair_tolerance_ms=float(self.get_parameter('pair_tolerance_ms').value),
                sample_stride=max(1, int(self.get_parameter('sample_stride').value)),
                max_pairs=max(0, int(self.get_parameter('max_pairs').value)),
            )

            rgb_dir = output_dir / 'rgb'
            thermal_raw_dir = output_dir / 'thermal_raw'
            thermal_color_dir = output_dir / 'thermal_color'
            output_dir.mkdir(parents=True, exist_ok=True)
            if bool(self.get_parameter('save_rgb').value):
                rgb_dir.mkdir(parents=True, exist_ok=True)
            if bool(self.get_parameter('save_thermal_raw').value):
                thermal_raw_dir.mkdir(parents=True, exist_ok=True)
            if bool(self.get_parameter('save_thermal_color').value):
                thermal_color_dir.mkdir(parents=True, exist_ok=True)

            manifest_path = output_dir / 'manifest.csv'
            log_every = max(1, int(self.get_parameter('log_every').value))

            with manifest_path.open('w', newline='', encoding='utf-8') as manifest_file:
                writer = csv.writer(manifest_file)
                writer.writerow(['index', 'pair_name', 'stamp_ns', 'rgb_path', 'thermal_raw_path', 'thermal_color_path'])

                for pair_index, pair in enumerate(bag_pairs, start=1):
                    stem = pair.name
                    extension = 'jpg' if image_format == 'jpeg' else image_format
                    rgb_path = rgb_dir / f'{stem}.{extension}'
                    thermal_raw_path = thermal_raw_dir / f'{stem}.png'
                    thermal_color_path = thermal_color_dir / f'{stem}.png'

                    if bool(self.get_parameter('save_rgb').value):
                        self._save_rgb_image(rgb_path, pair.rgb_image)
                    if bool(self.get_parameter('save_thermal_raw').value):
                        self._save_grayscale_image(thermal_raw_path, pair.thermal_image)
                    if bool(self.get_parameter('save_thermal_color').value):
                        self._save_thermal_color_preview(thermal_color_path, pair.thermal_image)

                    writer.writerow(
                        [
                            pair_index,
                            pair.name,
                            pair.stamp_ns,
                            str(rgb_path) if rgb_path.exists() else '',
                            str(thermal_raw_path) if thermal_raw_path.exists() else '',
                            str(thermal_color_path) if thermal_color_path.exists() else '',
                        ]
                    )

                    if pair_index == 1 or pair_index % log_every == 0:
                        self.get_logger().info(
                            f'Extraidos {pair_index}/{len(bag_pairs)} pares en {output_dir}'
                        )

            self.get_logger().info(f'Extraccion completada. Pares guardados: {len(bag_pairs)}')
            self.get_logger().info(f'Carpeta de salida: {output_dir}')
            self.get_logger().info(f'Manifest: {manifest_path}')
        except Exception as exc:
            self.get_logger().error(str(exc))
        finally:
            self._finished = True
            rclpy.shutdown()

    @staticmethod
    def _save_rgb_image(path: Path, image: np.ndarray) -> None:
        image_to_save = image
        if image.ndim == 3 and image.shape[2] == 3:
            image_to_save = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        if not cv2.imwrite(str(path), image_to_save):
            raise RuntimeError(f'No se pudo guardar la imagen RGB: {path}')

    @staticmethod
    def _save_grayscale_image(path: Path, image: np.ndarray) -> None:
        gray = ensure_grayscale(image)
        if not cv2.imwrite(str(path), gray):
            raise RuntimeError(f'No se pudo guardar la imagen termica: {path}')

    @staticmethod
    def _save_thermal_color_preview(path: Path, image: np.ndarray) -> None:
        gray = ensure_grayscale(image)
        color = cv2.applyColorMap(gray, cv2.COLORMAP_INFERNO)
        if not cv2.imwrite(str(path), color):
            raise RuntimeError(f'No se pudo guardar la previsualizacion termica: {path}')


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = BagImageExtractorNode()
    try:
        rclpy.spin(node)
    finally:
        if rclpy.ok():
            node.destroy_node()
            rclpy.shutdown()
