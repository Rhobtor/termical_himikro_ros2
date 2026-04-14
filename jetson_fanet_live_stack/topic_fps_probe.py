#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, HistoryPolicy, ReliabilityPolicy
from sensor_msgs.msg import Image


class TopicFpsProbe(Node):
    def __init__(self, topics: list[str]) -> None:
        super().__init__('topic_fps_probe')
        qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
        )
        self._counts = {topic: 0 for topic in topics}
        self._first_stamp = {topic: None for topic in topics}
        self._last_stamp = {topic: None for topic in topics}

        for topic in topics:
            self.create_subscription(Image, topic, self._make_cb(topic), qos)

    def _make_cb(self, topic: str):
        def cb(_msg: Image) -> None:
            now = time.monotonic()
            if self._first_stamp[topic] is None:
                self._first_stamp[topic] = now
            self._last_stamp[topic] = now
            self._counts[topic] += 1
        return cb

    def report(self, duration: float) -> None:
        for topic, count in self._counts.items():
            fps = count / duration if duration > 0 else 0.0
            print(f'{topic}: count={count} fps~={fps:.2f}')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Mide FPS aproximados de topics ROS 2 con QoS BEST_EFFORT.')
    parser.add_argument('--duration', type=float, default=6.0)
    parser.add_argument('--topic', action='append', required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rclpy.init()
    node = TopicFpsProbe(args.topic)
    end = time.monotonic() + args.duration
    try:
      while time.monotonic() < end:
          rclpy.spin_once(node, timeout_sec=0.2)
      node.report(args.duration)
    finally:
      node.destroy_node()
      rclpy.shutdown()


if __name__ == '__main__':
    main()