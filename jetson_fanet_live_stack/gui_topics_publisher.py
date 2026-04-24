#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
from typing import Optional

import cv2
import numpy as np
import rclpy
from geometry_msgs.msg import PoseArray
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage, Image
from std_msgs.msg import Float32MultiArray


class GuiTopicsPublisher(Node):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__('fanet_gui_topics_publisher')
        self._args = args
        self._overlay_size: Optional[tuple[int, int]] = None
        self._last_centroids: list[tuple[float, float, float]] = []
        self._last_distances_m: list[float] = []
        self._last_robot_positions: list[tuple[float, float, float]] = []

        sensor_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
        )

        self._rgb_pub = self.create_publisher(Image, args.rgb_output_topic, sensor_qos)
        self._thermal_pub = self.create_publisher(Image, args.thermal_output_topic, sensor_qos)
        self._rgb_compressed_pub = self.create_publisher(CompressedImage, args.rgb_compressed_output_topic, sensor_qos)
        self._thermal_compressed_pub = self.create_publisher(CompressedImage, args.thermal_compressed_output_topic, sensor_qos)

        self.create_subscription(Image, args.overlay_topic, self._on_overlay, sensor_qos)
        self.create_subscription(Image, args.rgb_topic, self._on_rgb, sensor_qos)
        self.create_subscription(Image, args.thermal_topic, self._on_thermal, sensor_qos)
        self.create_subscription(PoseArray, args.centroids_topic, self._on_centroids, 10)
        self.create_subscription(Float32MultiArray, args.distances_topic, self._on_distances, 10)
        self.create_subscription(PoseArray, args.robot_positions_topic, self._on_robot_positions, 10)

        self.get_logger().info(
            f'Publicando topics GUI anotados en {args.rgb_output_topic} y {args.thermal_output_topic}'
        )

    def _on_overlay(self, msg: Image) -> None:
        self._overlay_size = (int(msg.width), int(msg.height))

    def _on_centroids(self, msg: PoseArray) -> None:
        self._last_centroids = [
            (
                float(pose.position.x),
                float(pose.position.y),
                float(pose.position.z),
            )
            for pose in msg.poses
        ]

    def _on_distances(self, msg: Float32MultiArray) -> None:
        self._last_distances_m = [float(value) for value in msg.data]

    def _on_robot_positions(self, msg: PoseArray) -> None:
        self._last_robot_positions = [
            (
                float(pose.position.x),
                float(pose.position.y),
                float(pose.position.z),
            )
            for pose in msg.poses
        ]

    def _on_rgb(self, msg: Image) -> None:
        image = self._to_rgb8(msg)
        annotated = self._annotate_rgb(image)
        self._rgb_pub.publish(self._to_image_msg(annotated, msg.header, 'rgb8'))
        self._rgb_compressed_pub.publish(
            self._to_compressed_image_msg(annotated, msg.header, int(self._args.jpeg_quality))
        )

    def _on_thermal(self, msg: Image) -> None:
        mono = self._to_mono8(msg)
        colored_bgr = cv2.applyColorMap(mono, cv2.COLORMAP_INFERNO)
        annotated_bgr = self._annotate_bgr(colored_bgr)
        annotated_rgb = cv2.cvtColor(annotated_bgr, cv2.COLOR_BGR2RGB)
        self._thermal_pub.publish(self._to_image_msg(annotated_rgb, msg.header, 'rgb8'))
        self._thermal_compressed_pub.publish(
            self._to_compressed_image_msg(annotated_rgb, msg.header, int(self._args.jpeg_quality))
        )

    def _annotate_rgb(self, image: np.ndarray) -> np.ndarray:
        annotated = image.copy()
        annotated_bgr = cv2.cvtColor(annotated, cv2.COLOR_RGB2BGR)
        annotated_bgr = self._annotate_bgr(annotated_bgr)
        return cv2.cvtColor(annotated_bgr, cv2.COLOR_BGR2RGB)

    def _annotate_bgr(self, image: np.ndarray) -> np.ndarray:
        annotated = image.copy()

        scaled_centroids = []
        for centroid in self._last_centroids:
            scaled = self._scale_centroid(centroid, annotated.shape[1], annotated.shape[0])
            if scaled is not None:
                scaled_centroids.append(scaled)

        for index, (center_x, center_y, _area) in enumerate(scaled_centroids, start=1):
            cv2.drawMarker(
                annotated,
                (center_x, center_y),
                (0, 220, 255),
                markerType=cv2.MARKER_CROSS,
                markerSize=24,
                thickness=2,
            )
            label = self._build_person_label(index - 1)
            if label:
                cv2.putText(
                    annotated,
                    label,
                    (center_x + 12, max(20, center_y - 12)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (0, 220, 255),
                    2,
                    cv2.LINE_AA,
                )

        return annotated

    def _build_person_label(self, index: int) -> str:
        label_parts: list[str] = []
        if index < len(self._last_distances_m) and math.isfinite(self._last_distances_m[index]):
            label_parts.append(f'{self._last_distances_m[index]:.2f}m')
        if index < len(self._last_robot_positions):
            x_pos, y_pos, _z_pos = self._last_robot_positions[index]
            if math.isfinite(x_pos) and math.isfinite(y_pos):
                label_parts.append(f'({x_pos:.2f},{y_pos:.2f})')
        return ' '.join(label_parts)

    def _scale_centroid(
        self,
        centroid: tuple[float, float, float],
        target_width: int,
        target_height: int,
    ) -> Optional[tuple[int, int, int]]:
        source_size = self._overlay_size
        if source_size is None:
            return None

        source_width, source_height = source_size
        if source_width <= 0 or source_height <= 0:
            return None

        center_x, center_y, area = centroid
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
    def _to_compressed_image_msg(image: np.ndarray, header, jpeg_quality: int) -> CompressedImage:
        bgr_image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
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
    def _to_rgb8(msg: Image) -> np.ndarray:
        encoding = msg.encoding.lower()
        flat = np.frombuffer(msg.data, dtype=np.uint8)

        if encoding == 'mono8':
            rows = flat.reshape((int(msg.height), int(msg.step)))
            image = rows[:, : int(msg.width)].copy()
            return np.repeat(image[:, :, None], 3, axis=2)

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
        image = rows[:, : int(msg.width) * channels].reshape((int(msg.height), int(msg.width), channels)).copy()

        if encoding == 'rgb8':
            return image
        if encoding == 'bgr8':
            return image[..., ::-1].copy()
        if encoding == 'rgba8':
            return image[..., :3].copy()
        return image[..., [2, 1, 0]].copy()

    @staticmethod
    def _to_mono8(msg: Image) -> np.ndarray:
        if msg.encoding.lower() != 'mono8':
            raise ValueError(f'Encoding termico no soportado: {msg.encoding}')
        flat = np.frombuffer(msg.data, dtype=np.uint8)
        rows = flat.reshape((int(msg.height), int(msg.step)))
        return rows[:, : int(msg.width)].copy()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Publica RGB y termica anotados para una GUI ROS 2.')
    parser.add_argument('--overlay-topic', default='/fanet/segmentation/overlay')
    parser.add_argument('--rgb-topic', default='/zed/zed_node/left/image_rect_color')
    parser.add_argument('--thermal-topic', default='/fanet/raw/thermal')
    parser.add_argument('--centroids-topic', default='/fanet/person_centroids')
    parser.add_argument('--robot-positions-topic', default='/fanet/person_positions_robot')
    parser.add_argument('--distances-topic', default='/fanet/person_distances')
    parser.add_argument('--rgb-output-topic', default='/fanet/gui/rgb_annotated')
    parser.add_argument('--thermal-output-topic', default='/fanet/gui/thermal_annotated')
    parser.add_argument('--rgb-compressed-output-topic', default='/fanet/gui/rgb_annotated/compressed')
    parser.add_argument('--thermal-compressed-output-topic', default='/fanet/gui/thermal_annotated/compressed')
    parser.add_argument('--jpeg-quality', type=int, default=70)
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