#!/usr/bin/env python3
from __future__ import annotations

import argparse

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image


class ImageTopicViewer(Node):
    def __init__(self, topic: str, window_name: str) -> None:
        super().__init__('fanet_image_topic_viewer')
        self._window_name = window_name

        sensor_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
        )

        self.create_subscription(Image, topic, self._on_image, sensor_qos)
        cv2.namedWindow(self._window_name, cv2.WINDOW_NORMAL)
        self.get_logger().info(f'Visualizando imagen desde {topic}')

    def _on_image(self, msg: Image) -> None:
        image = self._to_bgr(msg)
        cv2.imshow(self._window_name, image)
        cv2.waitKey(1)

    @staticmethod
    def _to_bgr(msg: Image) -> np.ndarray:
        encoding = msg.encoding.lower()
        flat = np.frombuffer(msg.data, dtype=np.uint8)

        if encoding == 'mono8':
            rows = flat.reshape((int(msg.height), int(msg.step)))
            image = rows[:, : int(msg.width)].copy()
            return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

        if encoding not in ('rgb8', 'bgr8', 'rgba8', 'bgra8'):
            raise ValueError(f'Encoding no soportado: {msg.encoding}')

        rows = flat.reshape((int(msg.height), int(msg.step)))
        channels = 4 if encoding in ('rgba8', 'bgra8') else 3
        image = rows[:, : int(msg.width) * channels].reshape((int(msg.height), int(msg.width), channels)).copy()
        if encoding == 'rgb8':
            return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        if encoding == 'rgba8':
            return cv2.cvtColor(image, cv2.COLOR_RGBA2BGR)
        if encoding == 'bgra8':
            return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
        return image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Muestra un topic ROS 2 de imagen en una ventana OpenCV.')
    parser.add_argument('--topic', default='/fanet/gui/rgb_annotated')
    parser.add_argument('--window-name', default='fanet_image_viewer')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rclpy.init()
    node = ImageTopicViewer(args.topic, args.window_name)
    try:
        rclpy.spin(node)
    finally:
        cv2.destroyAllWindows()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
