#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image


class ThermalRtspPublisher(Node):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__('hikmicro_rtsp_ffmpeg_publisher')
        self._args = args
        sensor_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
        )
        self._publisher = self.create_publisher(Image, args.topic, sensor_qos)
        self._frame_size = int(args.width) * int(args.height)
        self._process = None
        self.get_logger().info(f'Publicando termica RTSP en {args.topic} desde {args.url}')

    def run(self) -> None:
        while rclpy.ok():
            try:
                self._run_once()
            except Exception as exc:
                self.get_logger().error(f'Fallo en stream termico: {exc}')
                time.sleep(1.0)

    def _run_once(self) -> None:
        command = [
            'ffmpeg',
            '-nostdin',
            '-hide_banner',
            '-loglevel',
            'error',
            '-rtsp_transport',
            self._args.transport,
            '-probesize',
            '32',
            '-analyzeduration',
            '0',
            '-fflags',
            'discardcorrupt',
            '-an',
            '-sn',
            '-dn',
            '-i',
            self._args.url,
            '-vf',
            'format=gray',
            '-pix_fmt',
            'gray',
            '-vsync',
            '0',
            '-f',
            'rawvideo',
            'pipe:1',
        ]

        self._process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        if self._process.stdout is None:
            raise RuntimeError('No se pudo abrir stdout de ffmpeg')

        min_period = 0.0 if self._args.fps <= 0.0 else 1.0 / self._args.fps
        last_pub = 0.0

        while rclpy.ok():
            frame = self._process.stdout.read(self._frame_size)
            if len(frame) != self._frame_size:
                raise RuntimeError('ffmpeg corto el stream termico o entrego frame incompleto')

            now = time.monotonic()
            if min_period > 0.0 and (now - last_pub) < min_period:
                continue

            msg = Image()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = 'thermal_optical_frame'
            msg.height = int(self._args.height)
            msg.width = int(self._args.width)
            msg.encoding = 'mono8'
            msg.is_bigendian = False
            msg.step = int(self._args.width)
            msg.data = frame
            self._publisher.publish(msg)
            last_pub = now

    def destroy_node(self):
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
        return super().destroy_node()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Publica la termica Hikmicro por ROS 2 desde RTSP.')
    parser.add_argument('--url', required=True)
    parser.add_argument('--topic', required=True)
    parser.add_argument('--transport', default='tcp')
    parser.add_argument('--width', type=int, default=640)
    parser.add_argument('--height', type=int, default=512)
    parser.add_argument('--fps', type=float, default=25.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rclpy.init()
    node = ThermalRtspPublisher(args)
    try:
        node.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()