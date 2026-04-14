#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image


class PairSyncBridge(Node):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__('fanet_pair_sync_bridge')
        self._args = args
        self._latest_rgb = None
        self._latest_rgb_time = 0.0
        self._latest_thermal = None
        self._latest_thermal_time = 0.0
        self._published_pairs = 0

        sensor_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
        )

        self._rgb_pub = self.create_publisher(Image, args.rgb_out, sensor_qos)
        self._thermal_pub = self.create_publisher(Image, args.thermal_out, sensor_qos)
        self.create_subscription(Image, args.rgb_in, self._on_rgb, sensor_qos)
        self.create_subscription(Image, args.thermal_in, self._on_thermal, sensor_qos)
        self.create_timer(1.0 / max(1e-3, args.rate), self._publish_pair)
        self.get_logger().info(
            f'Sincronizando {args.rgb_in} + {args.thermal_in} -> {args.rgb_out} + {args.thermal_out} @ {args.rate:.1f} Hz'
        )

    def _on_rgb(self, msg: Image) -> None:
        self._latest_rgb = msg
        self._latest_rgb_time = time.monotonic()

    def _on_thermal(self, msg: Image) -> None:
        self._latest_thermal = msg
        self._latest_thermal_time = time.monotonic()

    def _publish_pair(self) -> None:
        if self._latest_rgb is None or self._latest_thermal is None:
            return

        now = time.monotonic()
        if (now - self._latest_rgb_time) > 0.5 or (now - self._latest_thermal_time) > 0.5:
            return

        stamp = self.get_clock().now().to_msg()
        rgb_msg = copy.deepcopy(self._latest_rgb)
        thermal_msg = copy.deepcopy(self._latest_thermal)
        rgb_msg.header.stamp = stamp
        thermal_msg.header.stamp = stamp
        self._rgb_pub.publish(rgb_msg)
        self._thermal_pub.publish(thermal_msg)

        self._published_pairs += 1
        if (self._published_pairs % 50) == 0:
            self.get_logger().info(f'Pares sincronizados publicados: {self._published_pairs}')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Sincroniza RGB y térmica para FANet.')
    parser.add_argument('--rgb-in', required=True)
    parser.add_argument('--thermal-in', required=True)
    parser.add_argument('--rgb-out', required=True)
    parser.add_argument('--thermal-out', required=True)
    parser.add_argument('--rate', type=float, default=15.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rclpy.init()
    node = PairSyncBridge(args)
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()