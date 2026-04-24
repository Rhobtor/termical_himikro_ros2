#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
from typing import Optional

import cv2
import numpy as np
import rclpy
from geometry_msgs.msg import PointStamped
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage, Image
from std_msgs.msg import Float32


class GuiTopicsPublisher(Node):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__('fanet_gui_topics_publisher')
        self._args = args
        self._publish_rgb_image = bool(args.publish_rgb_image)
        self._publish_rgb_compressed = bool(args.publish_rgb_compressed)
        self._publish_thermal_image = bool(args.publish_thermal_image)
        self._publish_thermal_compressed = bool(args.publish_thermal_compressed)
        self._last_centroid: Optional[tuple[float, float, float]] = None
        self._last_distance_m: Optional[float] = None
        self._last_robot_position: Optional[tuple[float, float, float]] = None

        sensor_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
        )

        self._rgb_pub = self.create_publisher(Image, args.rgb_output_topic, sensor_qos) if self._publish_rgb_image else None
        self._thermal_pub = self.create_publisher(Image, args.thermal_output_topic, sensor_qos) if self._publish_thermal_image else None
        self._rgb_compressed_pub = (
            self.create_publisher(CompressedImage, args.rgb_compressed_output_topic, sensor_qos)
            if self._publish_rgb_compressed
            else None
        )
        self._thermal_compressed_pub = (
            self.create_publisher(CompressedImage, args.thermal_compressed_output_topic, sensor_qos)
            if self._publish_thermal_compressed
            else None
        )

        self.create_subscription(Image, args.rgb_topic, self._on_rgb, sensor_qos)
        if self._publish_thermal_image or self._publish_thermal_compressed:
            self.create_subscription(Image, args.thermal_topic, self._on_thermal, sensor_qos)
        self.create_subscription(PointStamped, args.centroid_topic, self._on_centroid, 10)
        self.create_subscription(Float32, args.distance_topic, self._on_distance, 10)
        self.create_subscription(PointStamped, args.robot_position_topic, self._on_robot_position, 10)

        self.get_logger().info(
            'GUI topics activos: '
            f'rgb={self._publish_rgb_image} '
            f'rgb_compressed={self._publish_rgb_compressed} '
            f'thermal={self._publish_thermal_image} '
            f'thermal_compressed={self._publish_thermal_compressed}'
        )

    def _on_centroid(self, msg: PointStamped) -> None:
        self._last_centroid = (float(msg.point.x), float(msg.point.y), float(msg.point.z))

    def _on_distance(self, msg: Float32) -> None:
        self._last_distance_m = float(msg.data)

    def _on_robot_position(self, msg: PointStamped) -> None:
        self._last_robot_position = (float(msg.point.x), float(msg.point.y), float(msg.point.z))

    def _on_rgb(self, msg: Image) -> None:
        image, encoding = self._to_color_image(msg)
        annotated = self._annotate_color(image, encoding)

        if self._rgb_pub is not None:
            self._rgb_pub.publish(self._to_image_msg(annotated, msg.header, encoding))

        if self._rgb_compressed_pub is not None:
            self._rgb_compressed_pub.publish(
                self._to_compressed_image_msg(annotated, msg.header, int(self._args.jpeg_quality), encoding)
            )

    def _on_thermal(self, msg: Image) -> None:
        mono = self._to_mono8(msg)
        colored_bgr = cv2.applyColorMap(mono, cv2.COLORMAP_INFERNO)
        annotated_bgr = self._annotate_color(colored_bgr, 'bgr8')
        if self._thermal_pub is not None:
            self._thermal_pub.publish(self._to_image_msg(annotated_bgr, msg.header, 'bgr8'))
        if self._thermal_compressed_pub is not None:
            self._thermal_compressed_pub.publish(
                self._to_compressed_image_msg(annotated_bgr, msg.header, int(self._args.jpeg_quality), 'bgr8')
            )

    def _annotate_color(self, image: np.ndarray, encoding: str) -> np.ndarray:
        annotated = np.array(image, copy=True, order='C')
        color = (0, 220, 255) if encoding == 'bgr8' else (255, 220, 0)

        scaled = self._scale_centroid(annotated.shape[1], annotated.shape[0])
        if scaled is None:
            return annotated

        center_x, center_y, _area = scaled
        cv2.drawMarker(
            annotated,
            (center_x, center_y),
            color,
            markerType=cv2.MARKER_CROSS,
            markerSize=24,
            thickness=2,
        )
        label = self._build_person_label()
        if label:
            cv2.putText(
                annotated,
                label,
                (center_x + 12, max(20, center_y - 12)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                color,
                2,
                cv2.LINE_AA,
            )

        return annotated

    def _build_person_label(self) -> str:
        label_parts: list[str] = []
        if self._last_distance_m is not None and math.isfinite(self._last_distance_m):
            label_parts.append(f'{self._last_distance_m:.2f}m')
        if self._last_robot_position is not None:
            x_pos, y_pos, _z_pos = self._last_robot_position
            if math.isfinite(x_pos) and math.isfinite(y_pos):
                label_parts.append(f'({x_pos:.2f},{y_pos:.2f})')
        return ' '.join(label_parts)

    def _scale_centroid(
        self,
        target_width: int,
        target_height: int,
    ) -> Optional[tuple[int, int, int]]:
        if self._last_centroid is None:
            return None

        source_width = max(1, int(self._args.model_width))
        source_height = max(1, int(self._args.model_height))
        if source_width <= 0 or source_height <= 0:
            return None

        center_x, center_y, area = self._last_centroid
        scaled_x = int(round(center_x * target_width / source_width))
        scaled_y = int(round(center_y * target_height / source_height))
        scaled_x = min(max(scaled_x, 0), target_width - 1)
        scaled_y = min(max(scaled_y, 0), target_height - 1)
        return scaled_x, scaled_y, int(round(area))

    @staticmethod
    def _to_image_msg(image: np.ndarray, header, encoding: str) -> Image:
        msg = Image()
        msg.header = header
        msg.height = int(image.shape[0])
        msg.width = int(image.shape[1])
        msg.encoding = encoding
        msg.is_bigendian = False
        channels = 1 if image.ndim == 2 else image.shape[2]
        msg.step = int(image.shape[1] * channels)
        msg.data = image.tobytes()
        return msg

    @staticmethod
    def _to_compressed_image_msg(image: np.ndarray, header, jpeg_quality: int, encoding: str) -> CompressedImage:
        bgr_image = image if encoding == 'bgr8' else cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        success, encoded = cv2.imencode(
            '.jpg',
            bgr_image,
            [int(cv2.IMWRITE_JPEG_QUALITY), max(1, min(100, jpeg_quality))],
        )
        if not success:
            raise RuntimeError('No se pudo comprimir la imagen GUI a JPEG')

        msg = CompressedImage()
        msg.header = header
        msg.format = 'jpeg'
        msg.data = encoded.tobytes()
        return msg

    @staticmethod
    def _to_color_image(msg: Image) -> tuple[np.ndarray, str]:
        encoding = msg.encoding.lower()
        flat = np.frombuffer(msg.data, dtype=np.uint8)

        if encoding == 'mono8':
            rows = flat.reshape((int(msg.height), int(msg.step)))
            image = rows[:, : int(msg.width)]
            return np.repeat(image[:, :, None], 3, axis=2), 'rgb8'

        channels_map = {
            'rgb8': 3,
            'bgr8': 3,
            'rgba8': 4,
            'bgra8': 4,
        }
        channels = channels_map.get(encoding)
        if channels is None:
            raise ValueError(f'Encoding no soportado: {msg.encoding}')

        rows = flat.reshape((int(msg.height), int(msg.step)))
        image = rows[:, : int(msg.width) * channels].reshape((int(msg.height), int(msg.width), channels))

        if encoding == 'rgb8':
            return image, 'rgb8'
        if encoding == 'bgr8':
            return image, 'bgr8'
        if encoding == 'rgba8':
            return image[..., :3], 'rgb8'
        return image[..., :3], 'bgr8'

    @staticmethod
    def _to_mono8(msg: Image) -> np.ndarray:
        if msg.encoding.lower() != 'mono8':
            raise ValueError(f'Encoding termico no soportado: {msg.encoding}')
        flat = np.frombuffer(msg.data, dtype=np.uint8)
        rows = flat.reshape((int(msg.height), int(msg.step)))
        return rows[:, : int(msg.width)].copy()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Publica RGB y termica anotados para una GUI ROS 2.')
    parser.add_argument('--rgb-topic', default='/zed/zed_node/left/image_rect_color')
    parser.add_argument('--thermal-topic', default='/fanet/raw/thermal')
    parser.add_argument('--centroid-topic', default='/fanet/person_centroid')
    parser.add_argument('--robot-position-topic', default='/fanet/person_position_robot')
    parser.add_argument('--distance-topic', default='/fanet/person_distance')
    parser.add_argument('--rgb-output-topic', default='/fanet/gui/rgb_annotated')
    parser.add_argument('--thermal-output-topic', default='/fanet/gui/thermal_annotated')
    parser.add_argument('--rgb-compressed-output-topic', default='/fanet/gui/rgb_annotated/compressed')
    parser.add_argument('--thermal-compressed-output-topic', default='/fanet/gui/thermal_annotated/compressed')
    parser.add_argument('--model-width', type=int, default=448)
    parser.add_argument('--model-height', type=int, default=352)
    parser.add_argument('--jpeg-quality', type=int, default=70)
    parser.add_argument('--publish-rgb-image', type=int, choices=(0, 1), default=1)
    parser.add_argument('--publish-rgb-compressed', type=int, choices=(0, 1), default=1)
    parser.add_argument('--publish-thermal-image', type=int, choices=(0, 1), default=1)
    parser.add_argument('--publish-thermal-compressed', type=int, choices=(0, 1), default=1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rclpy.init()
    node = GuiTopicsPublisher(args)
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()