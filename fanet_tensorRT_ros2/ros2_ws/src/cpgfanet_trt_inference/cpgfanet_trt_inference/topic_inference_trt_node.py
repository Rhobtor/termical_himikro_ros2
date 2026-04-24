from __future__ import annotations

from pathlib import Path
import time

import cv2
import numpy as np
import rclpy
from geometry_msgs.msg import PointStamped, Pose, PoseArray
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import Int32

from .trt_runtime import TensorRTRuntime, TensorRTRuntimeConfig


class TopicInferenceTrtNode(Node):
    def __init__(self) -> None:
        super().__init__('cpgfanet_trt_topic_inference')

        self.declare_parameter('engine_path', '')
        self.declare_parameter('input_width', 448)
        self.declare_parameter('input_height', 352)
        self.declare_parameter('rgb_scale', 255.0)
        self.declare_parameter('thermal_scale', 255.0)
        self.declare_parameter('rgb_topic', '/fanet/input/rgb')
        self.declare_parameter('thermal_topic', '/fanet/input/thermal')
        self.declare_parameter('person_centroid_topic', '/fanet/person_centroid')
        self.declare_parameter('person_centroids_topic', '/fanet/person_centroids')
        self.declare_parameter('person_count_topic', '/fanet/person_count')
        self.declare_parameter('publish_person_centroid', True)
        self.declare_parameter('publish_person_centroids', True)
        self.declare_parameter('publish_person_count', True)
        self.declare_parameter('person_class_index', 2)
        self.declare_parameter('person_min_pixels', 72)
        self.declare_parameter('person_min_bbox_width', 8)
        self.declare_parameter('person_min_bbox_height', 16)
        self.declare_parameter('person_morph_open_kernel', 1)
        self.declare_parameter('person_morph_close_kernel', 3)
        self.declare_parameter('enable_perf_logging', True)
        self.declare_parameter('perf_log_period_s', 5.0)
        self.declare_parameter('max_pending_pairs', 2)

        self._image_size = (
            int(self.get_parameter('input_width').value),
            int(self.get_parameter('input_height').value),
        )
        self._pending_rgb: dict[int, Image] = {}
        self._pending_thermal: dict[int, Image] = {}
        self._processed_pairs = 0
        self._received_rgb = 0
        self._received_thermal = 0
        self._dropped_pending = 0
        self._last_perf_log = time.perf_counter()
        self._last_total_ms = 0.0

        self._runtime = TensorRTRuntime(
            TensorRTRuntimeConfig(engine_path=Path(str(self.get_parameter('engine_path').value)))
        )

        sensor_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.BEST_EFFORT,
        )
        self.create_subscription(Image, str(self.get_parameter('rgb_topic').value), self._on_rgb, sensor_qos)
        self.create_subscription(Image, str(self.get_parameter('thermal_topic').value), self._on_thermal, sensor_qos)
        self.person_centroid_pub = self.create_publisher(
            PointStamped,
            str(self.get_parameter('person_centroid_topic').value),
            1,
        )
        self.person_centroids_pub = self.create_publisher(
            PoseArray,
            str(self.get_parameter('person_centroids_topic').value),
            1,
        )
        self.person_count_pub = self.create_publisher(
            Int32,
            str(self.get_parameter('person_count_topic').value),
            1,
        )

        self.get_logger().info(
            f'Nodo TensorRT inicializado con engine {self.get_parameter("engine_path").value} '
            f'entrada={self._runtime.input_shape} salida={self._runtime.output_shape}'
        )

    def _on_rgb(self, msg: Image) -> None:
        key = self._stamp_to_key(msg)
        self._received_rgb += 1
        self._pending_rgb[key] = msg
        self._trim_pending()
        self._try_infer(key)

    def _on_thermal(self, msg: Image) -> None:
        key = self._stamp_to_key(msg)
        self._received_thermal += 1
        self._pending_thermal[key] = msg
        self._trim_pending()
        self._try_infer(key)

    @staticmethod
    def _stamp_to_key(msg: Image) -> int:
        return int(msg.header.stamp.sec) * 1_000_000_000 + int(msg.header.stamp.nanosec)

    def _trim_pending(self) -> None:
        max_pending = max(1, int(self.get_parameter('max_pending_pairs').value))
        while len(self._pending_rgb) > max_pending:
            oldest_key = min(self._pending_rgb)
            self._pending_rgb.pop(oldest_key, None)
            self._dropped_pending += 1
        while len(self._pending_thermal) > max_pending:
            oldest_key = min(self._pending_thermal)
            self._pending_thermal.pop(oldest_key, None)
            self._dropped_pending += 1

    def _try_infer(self, key: int) -> None:
        rgb_msg = self._pending_rgb.pop(key, None)
        thermal_msg = self._pending_thermal.pop(key, None)
        if rgb_msg is None or thermal_msg is None:
            if rgb_msg is not None:
                self._pending_rgb[key] = rgb_msg
            if thermal_msg is not None:
                self._pending_thermal[key] = thermal_msg
            return

        total_start = time.perf_counter()
        rgb = self._image_msg_to_numpy(rgb_msg)
        thermal = self._image_msg_to_numpy(thermal_msg)
        input_tensor, _rgb_resized = self._preprocess_pair(rgb, thermal)
        mask = self._runtime.infer(input_tensor)
        person_instances = self._extract_person_instances(mask)
        primary_person = person_instances[0] if person_instances else None
        self._processed_pairs += 1
        self._last_total_ms = (time.perf_counter() - total_start) * 1000.0
        self._maybe_log_performance()
        if bool(self.get_parameter('publish_person_centroids').value):
            self.person_centroids_pub.publish(
                self._centroids_to_pose_array(person_instances, rgb_msg.header.stamp, rgb_msg.header.frame_id)
            )
        if bool(self.get_parameter('publish_person_count').value):
            count_msg = Int32()
            count_msg.data = len(person_instances)
            self.person_count_pub.publish(count_msg)
        if primary_person is None:
            return

        if bool(self.get_parameter('publish_person_centroid').value):
            self.person_centroid_pub.publish(self._centroid_to_point(primary_person, rgb_msg.header.stamp, rgb_msg.header.frame_id))

    def _maybe_log_performance(self) -> None:
        if not bool(self.get_parameter('enable_perf_logging').value):
            return
        now = time.perf_counter()
        period_s = max(0.5, float(self.get_parameter('perf_log_period_s').value))
        if (now - self._last_perf_log) < period_s:
            return
        output_fps = self._processed_pairs / max(now - self._last_perf_log, 1e-6)
        self.get_logger().info(
            'Rendimiento TensorRT FANet | total={:.1f} ms | fps_out={:.2f} | processed={} | rgb_rx={} | tir_rx={} | dropped={}'.format(
                self._last_total_ms,
                output_fps,
                self._processed_pairs,
                self._received_rgb,
                self._received_thermal,
                self._dropped_pending,
            )
        )
        self._processed_pairs = 0
        self._received_rgb = 0
        self._received_thermal = 0
        self._dropped_pending = 0
        self._last_perf_log = now

    def _preprocess_pair(self, rgb_image: np.ndarray, thermal_image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        width, height = self._image_size
        if rgb_image.shape[:2] != (height, width):
            rgb_image = cv2.resize(rgb_image, (width, height), interpolation=cv2.INTER_LINEAR)
        if thermal_image.shape[:2] != (height, width):
            thermal_image = cv2.resize(thermal_image, (width, height), interpolation=cv2.INTER_LINEAR)

        rgb_image = np.ascontiguousarray(rgb_image)
        thermal_image = np.ascontiguousarray(thermal_image)

        stacked = np.empty((1, 4, height, width), dtype=np.float32)
        stacked[0, :3] = rgb_image.astype(np.float32).transpose(2, 0, 1) / float(self.get_parameter('rgb_scale').value)
        stacked[0, 3] = thermal_image.astype(np.float32) / float(self.get_parameter('thermal_scale').value)
        return stacked, rgb_image

    def _extract_person_instances(self, mask: np.ndarray) -> list[dict[str, float | int | tuple[int, int, int, int]]]:
        person_class_index = int(self.get_parameter('person_class_index').value)
        min_pixels = max(1, int(self.get_parameter('person_min_pixels').value))
        min_bbox_width = max(1, int(self.get_parameter('person_min_bbox_width').value))
        min_bbox_height = max(1, int(self.get_parameter('person_min_bbox_height').value))

        binary = (mask == person_class_index).astype(np.uint8)
        if not np.any(binary):
            return []

        open_kernel_size = max(0, int(self.get_parameter('person_morph_open_kernel').value))
        close_kernel_size = max(0, int(self.get_parameter('person_morph_close_kernel').value))
        if open_kernel_size > 1:
            open_kernel = np.ones((open_kernel_size, open_kernel_size), dtype=np.uint8)
            binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, open_kernel)
        if close_kernel_size > 1:
            close_kernel = np.ones((close_kernel_size, close_kernel_size), dtype=np.uint8)
            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, close_kernel)
        if not np.any(binary):
            return []

        component_count, _labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
        instances: list[dict[str, float | int | tuple[int, int, int, int]]] = []
        for label in range(1, component_count):
            area = int(stats[label, cv2.CC_STAT_AREA])
            width = int(stats[label, cv2.CC_STAT_WIDTH])
            height = int(stats[label, cv2.CC_STAT_HEIGHT])
            if area < min_pixels or width < min_bbox_width or height < min_bbox_height:
                continue
            left = int(stats[label, cv2.CC_STAT_LEFT])
            top = int(stats[label, cv2.CC_STAT_TOP])
            centroid_x = float(centroids[label][0])
            centroid_y = float(centroids[label][1])
            instances.append(
                {
                    'centroid_x': centroid_x,
                    'centroid_y': centroid_y,
                    'area': area,
                    'bbox': (left, top, width, height),
                }
            )
        instances.sort(key=lambda item: int(item['area']), reverse=True)
        return instances

    @staticmethod
    def _centroid_to_point(centroid, stamp, frame_id: str) -> PointStamped:
        msg = PointStamped()
        msg.header.stamp = stamp
        msg.header.frame_id = frame_id
        msg.point.x = float(centroid['centroid_x'])
        msg.point.y = float(centroid['centroid_y'])
        msg.point.z = float(centroid['area'])
        return msg

    @staticmethod
    def _centroids_to_pose_array(centroids, stamp, frame_id: str) -> PoseArray:
        msg = PoseArray()
        msg.header.stamp = stamp
        msg.header.frame_id = frame_id
        for index, centroid in enumerate(centroids):
            pose = Pose()
            pose.position.x = float(centroid['centroid_x'])
            pose.position.y = float(centroid['centroid_y'])
            pose.position.z = float(centroid['area'])
            pose.orientation.w = 1.0
            pose.orientation.z = float(index)
            msg.poses.append(pose)
        return msg

    @staticmethod
    def _image_msg_to_numpy(msg: Image) -> np.ndarray:
        if msg.encoding not in ('rgb8', 'bgr8', 'mono8'):
            raise ValueError(f'Encoding no soportado: {msg.encoding}')

        flat = np.frombuffer(msg.data, dtype=np.uint8)
        rows = flat.reshape((int(msg.height), int(msg.step)))
        if msg.encoding == 'mono8':
            return rows[:, : int(msg.width)].copy()
        image = rows[:, : int(msg.width) * 3].reshape((int(msg.height), int(msg.width), 3)).copy()
        if msg.encoding == 'bgr8':
            return image[..., ::-1].copy()
        return image


def main(args=None) -> None:
    rclpy.init(args=args)
    node = TopicInferenceTrtNode()
    rclpy.spin(node)


if __name__ == '__main__':
    main()