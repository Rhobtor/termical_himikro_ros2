#!/usr/bin/env python3
from __future__ import annotations

import argparse

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image


class ThermalTopicViewer(Node):
    def __init__(self, topic: str, window_name: str, colorize: bool) -> None:
        super().__init__('fanet_thermal_topic_viewer')
        self._window_name = window_name
        self._colorize = colorize

        sensor_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
        )

        self.create_subscription(Image, topic, self._on_image, sensor_qos)
        cv2.namedWindow(self._window_name, cv2.WINDOW_NORMAL)
        self.get_logger().info(f'Visualizando termica desde {topic}')

    def _on_image(self, msg: Image) -> None:
        if msg.encoding != 'mono8':
            raise ValueError(f'Encoding termico no soportado: {msg.encoding}')

        flat = np.frombuffer(msg.data, dtype=np.uint8)
        rows = flat.reshape((int(msg.height), int(msg.step)))
        image = rows[:, : int(msg.width)].copy()

        if self._colorize:
            display = cv2.applyColorMap(image, cv2.COLORMAP_INFERNO)
        else:
            display = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

        cv2.imshow(self._window_name, display)
        cv2.waitKey(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Muestra una imagen termica ROS 2 con QoS BEST_EFFORT.')
    parser.add_argument('--topic', default='/fanet/raw/thermal')
    parser.add_argument('--window-name', default='fanet_thermal_viewer')
    parser.add_argument('--colorize', action='store_true')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rclpy.init()
    node = ThermalTopicViewer(args.topic, args.window_name, args.colorize)
    try:
        rclpy.spin(node)
    finally:
        cv2.destroyAllWindows()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()