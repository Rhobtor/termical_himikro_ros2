#!/usr/bin/env python3
from __future__ import annotations

import argparse

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image


class RgbTopicAdapter(Node):
    def __init__(self, input_topic: str, output_topic: str) -> None:
        super().__init__('fanet_rgb_topic_adapter')
        self._output_topic = output_topic

        sensor_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
        )

        self._publisher = self.create_publisher(Image, output_topic, sensor_qos)
        self._subscription = self.create_subscription(Image, input_topic, self._on_image, sensor_qos)
        self._logged_encoding = False
        self.get_logger().info(f'Adaptando RGB {input_topic} -> {output_topic}')

    def _on_image(self, msg: Image) -> None:
        if not self._logged_encoding:
            self.get_logger().info(f'Encoding recibido en ZED: {msg.encoding}')
            self._logged_encoding = True

        rgb = self._to_rgb8(msg)

        out = Image()
        out.header = msg.header
        out.height = int(rgb.shape[0])
        out.width = int(rgb.shape[1])
        out.encoding = 'rgb8'
        out.is_bigendian = False
        out.step = int(rgb.shape[1] * 3)
        out.data = rgb.tobytes()
        self._publisher.publish(out)

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
            raise ValueError(f'Encoding no soportado por el bridge: {msg.encoding}')

        rows = flat.reshape((int(msg.height), int(msg.step)))
        image = rows[:, : int(msg.width) * channels].reshape((int(msg.height), int(msg.width), channels)).copy()

        if encoding == 'rgb8':
            return image
        if encoding == 'bgr8':
            return image[..., ::-1].copy()
        if encoding == 'rgba8':
            return image[..., :3].copy()
        return image[..., [2, 1, 0]].copy()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Adapta la imagen RGB de ZED a rgb8 para FANet.')
    parser.add_argument('--input', required=True, help='Topic de entrada RGB de ZED.')
    parser.add_argument('--output', required=True, help='Topic de salida normalizado en rgb8.')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rclpy.init()
    node = RgbTopicAdapter(input_topic=args.input, output_topic=args.output)
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
