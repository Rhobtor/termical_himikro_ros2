#!/usr/bin/env python3
from __future__ import annotations

import argparse

import cv2
import numpy as np
import rclpy
from geometry_msgs.msg import PoseArray
from geometry_msgs.msg import PointStamped
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image


class PersonOverlayViewer(Node):
    def __init__(self, overlay_topic: str, centroid_topic: str, window_name: str) -> None:
        super().__init__('fanet_person_overlay_viewer')
        self._window_name = window_name
        self._last_centroid: PointStamped | None = None
        self._last_centroids: list[tuple[int, int, int]] = []

        sensor_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
        )

        self.create_subscription(Image, overlay_topic, self._on_overlay, sensor_qos)
        self.create_subscription(PointStamped, centroid_topic, self._on_centroid, 10)
        self.create_subscription(PoseArray, centroid_topic + 's', self._on_centroids, 10)

        cv2.namedWindow(self._window_name, cv2.WINDOW_NORMAL)
        self.get_logger().info(
            f'Visualizando {overlay_topic} con centroides desde {centroid_topic}'
        )

    def _on_centroid(self, msg: PointStamped) -> None:
        self._last_centroid = msg

    def _on_centroids(self, msg: PoseArray) -> None:
        self._last_centroids = [
            (
                int(round(pose.position.x)),
                int(round(pose.position.y)),
                int(round(pose.position.z)),
            )
            for pose in msg.poses
        ]

    def _on_overlay(self, msg: Image) -> None:
        image = self._image_msg_to_bgr(msg)

        centroids = self._last_centroids
        if not centroids and self._last_centroid is not None:
            centroids = [(
                int(round(self._last_centroid.point.x)),
                int(round(self._last_centroid.point.y)),
                int(round(self._last_centroid.point.z)),
            )]

        palette = [
            (0, 255, 0),
            (0, 200, 255),
            (255, 180, 0),
            (255, 80, 80),
            (180, 80, 255),
            (80, 255, 180),
        ]
        for index, (center_x, center_y, area_pixels) in enumerate(centroids, start=1):
            color = palette[(index - 1) % len(palette)]
            cv2.drawMarker(
                image,
                (center_x, center_y),
                color,
                markerType=cv2.MARKER_CROSS,
                markerSize=20,
                thickness=2,
            )
            cv2.putText(
                image,
                f'P{index} px=({center_x},{center_y}) area={area_pixels}px',
                (10, 28 + 26 * (index - 1)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                color,
                2,
                cv2.LINE_AA,
            )

        cv2.imshow(self._window_name, image)
        cv2.waitKey(1)

    @staticmethod
    def _image_msg_to_bgr(msg: Image) -> np.ndarray:
        if msg.encoding not in ('rgb8', 'bgr8', 'mono8'):
            raise ValueError(f'Encoding no soportado: {msg.encoding}')

        channels = 1 if msg.encoding == 'mono8' else 3
        row_width = int(msg.step)
        flat = np.frombuffer(msg.data, dtype=np.uint8)
        rows = flat.reshape((int(msg.height), row_width))

        if channels == 1:
            image = rows[:, : int(msg.width)].copy()
            return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

        image = rows[:, : int(msg.width) * channels].reshape((int(msg.height), int(msg.width), channels)).copy()
        if msg.encoding == 'rgb8':
            return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        return image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Muestra overlay de FANet con centroid de persona.')
    parser.add_argument('--overlay-topic', default='/fanet/segmentation/overlay')
    parser.add_argument('--centroid-topic', default='/fanet/person_centroid')
    parser.add_argument('--window-name', default='fanet_person_overlay')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rclpy.init()
    node = PersonOverlayViewer(args.overlay_topic, args.centroid_topic, args.window_name)
    try:
        rclpy.spin(node)
    finally:
        cv2.destroyAllWindows()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()