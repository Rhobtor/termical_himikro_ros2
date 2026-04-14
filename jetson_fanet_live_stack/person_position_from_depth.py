#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
from typing import Optional

import numpy as np
import rclpy
from geometry_msgs.msg import PoseArray
from geometry_msgs.msg import PointStamped
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import Float32


class PersonPositionFromDepth(Node):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__('fanet_person_position_from_depth')
        self._args = args
        self._depth_msg: Optional[Image] = None
        self._camera_info: Optional[CameraInfo] = None
        self._overlay_size: Optional[tuple[int, int]] = None
        self._last_centroids: list[tuple[float, float, float]] = []

        sensor_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
        )

        self._camera_pub = self.create_publisher(PointStamped, args.camera_position_topic, 10)
        self._robot_pub = self.create_publisher(PointStamped, args.robot_position_topic, 10)
        self._distance_pub = self.create_publisher(Float32, args.distance_topic, 10)

        self.create_subscription(Image, args.depth_topic, self._on_depth, sensor_qos)
        self.create_subscription(CameraInfo, args.camera_info_topic, self._on_camera_info, sensor_qos)
        self.create_subscription(Image, args.overlay_topic, self._on_overlay, sensor_qos)
        self.create_subscription(PointStamped, args.centroid_topic, self._on_centroid, 10)
        self.create_subscription(PoseArray, args.centroids_topic, self._on_centroids, 10)

        self.get_logger().info(
            f'Calculando posicion 3D desde {args.centroid_topic} usando {args.depth_topic} y {args.camera_info_topic}'
        )

    def _on_depth(self, msg: Image) -> None:
        self._depth_msg = msg

    def _on_camera_info(self, msg: CameraInfo) -> None:
        self._camera_info = msg

    def _on_overlay(self, msg: Image) -> None:
        self._overlay_size = (int(msg.width), int(msg.height))

    def _on_centroids(self, msg: PoseArray) -> None:
        self._last_centroids = [
            (float(pose.position.x), float(pose.position.y), float(pose.position.z))
            for pose in msg.poses
        ]

    def _on_centroid(self, msg: PointStamped) -> None:
        if self._depth_msg is None or self._camera_info is None or self._overlay_size is None:
            return

        candidates = self._last_centroids or [(float(msg.point.x), float(msg.point.y), float(msg.point.z))]
        best = self._select_closest_candidate(candidates)
        if best is None:
            return

        x_cam, y_cam, z_cam = best

        camera_point = PointStamped()
        camera_point.header.stamp = msg.header.stamp
        camera_point.header.frame_id = self._depth_msg.header.frame_id or msg.header.frame_id
        camera_point.point.x = float(x_cam)
        camera_point.point.y = float(y_cam)
        camera_point.point.z = float(z_cam)
        self._camera_pub.publish(camera_point)

        robot_point = PointStamped()
        robot_point.header.stamp = camera_point.header.stamp
        robot_point.header.frame_id = self._args.robot_frame_id
        robot_point.point.x = float(z_cam)
        robot_point.point.y = float(-x_cam)
        robot_point.point.z = float(-y_cam)
        self._robot_pub.publish(robot_point)

        distance = Float32()
        distance.data = float(math.sqrt(x_cam * x_cam + y_cam * y_cam + z_cam * z_cam))
        self._distance_pub.publish(distance)

    def _select_closest_candidate(self, candidates: list[tuple[float, float, float]]) -> Optional[tuple[float, float, float]]:
        best_point = None
        best_distance = None

        for image_x, image_y, _area in candidates:
            projected = self._project_image_centroid(float(image_x), float(image_y))
            if projected is None:
                continue
            x_cam, y_cam, z_cam = projected
            distance = math.sqrt(x_cam * x_cam + y_cam * y_cam + z_cam * z_cam)
            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_point = projected

        return best_point

    def _project_image_centroid(self, centroid_x: float, centroid_y: float) -> Optional[tuple[float, float, float]]:
        depth = self._depth_msg
        camera_info = self._camera_info
        model_size = self._overlay_size
        if depth is None or camera_info is None or model_size is None:
            return None

        model_width, model_height = model_size
        if model_width <= 0 or model_height <= 0:
            return None

        depth_width = int(depth.width)
        depth_height = int(depth.height)
        u = int(round(centroid_x * depth_width / model_width))
        v = int(round(centroid_y * depth_height / model_height))
        u = min(max(u, 0), depth_width - 1)
        v = min(max(v, 0), depth_height - 1)

        depth_value_m = self._sample_depth_meters(depth, u, v)
        if depth_value_m is None:
            return None

        fx = float(camera_info.k[0])
        fy = float(camera_info.k[4])
        cx = float(camera_info.k[2])
        cy = float(camera_info.k[5])
        if fx == 0.0 or fy == 0.0:
            return None

        x_cam = (u - cx) * depth_value_m / fx
        y_cam = (v - cy) * depth_value_m / fy
        z_cam = depth_value_m
        return float(x_cam), float(y_cam), float(z_cam)

    def _sample_depth_meters(self, msg: Image, center_u: int, center_v: int) -> Optional[float]:
        if msg.encoding not in ('32FC1', '16UC1'):
            return None

        if msg.encoding == '32FC1':
            dtype = np.float32
            scale = 1.0
        else:
            dtype = np.uint16
            scale = 0.001

        row_stride = int(msg.step) // np.dtype(dtype).itemsize
        array = np.frombuffer(msg.data, dtype=dtype).reshape((int(msg.height), row_stride))[:, : int(msg.width)]

        radius = max(0, int(self._args.search_radius))
        u0 = max(0, center_u - radius)
        u1 = min(int(msg.width), center_u + radius + 1)
        v0 = max(0, center_v - radius)
        v1 = min(int(msg.height), center_v + radius + 1)
        window = array[v0:v1, u0:u1].astype(np.float32) * scale
        valid = window[np.isfinite(window) & (window > 0.05) & (window < float(self._args.max_depth_m))]
        if valid.size == 0:
            return None
        return float(np.median(valid))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Convierte centroides 2D en posicion 3D usando profundidad ZED.')
    parser.add_argument('--centroid-topic', default='/fanet/person_centroid')
    parser.add_argument('--centroids-topic', default='/fanet/person_centroids')
    parser.add_argument('--overlay-topic', default='/fanet/segmentation/overlay')
    parser.add_argument('--depth-topic', default='/zed/zed_node/depth/depth_registered')
    parser.add_argument('--camera-info-topic', default='/zed/zed_node/depth/camera_info')
    parser.add_argument('--camera-position-topic', default='/fanet/person_position_camera')
    parser.add_argument('--robot-position-topic', default='/fanet/person_position_robot')
    parser.add_argument('--distance-topic', default='/fanet/person_distance')
    parser.add_argument('--robot-frame-id', default='robot_same_origin_frame')
    parser.add_argument('--search-radius', type=int, default=3)
    parser.add_argument('--max-depth-m', type=float, default=20.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rclpy.init()
    node = PersonPositionFromDepth(args)
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()