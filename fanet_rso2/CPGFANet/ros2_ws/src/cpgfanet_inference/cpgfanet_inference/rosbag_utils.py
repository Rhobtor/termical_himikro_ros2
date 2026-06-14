from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

import numpy as np


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class BagImagePair:
    name: str
    stamp_ns: int
    rgb_image: np.ndarray
    thermal_image: np.ndarray


@dataclass(frozen=True)
class StereoCalibration:
    rgb_camera_matrix: np.ndarray
    rgb_distortion: np.ndarray
    thermal_camera_matrix: np.ndarray
    thermal_distortion: np.ndarray
    thermal_to_rgb_rotation: np.ndarray
    thermal_to_rgb_translation_m: np.ndarray


def load_rosbag_image_pairs(
    bag_path: Path,
    rgb_topic: str,
    thermal_topic: str,
    pair_tolerance_ms: float,
    sample_stride: int,
    max_pairs: int,
) -> List[BagImagePair]:
    try:
        import rosbag2_py
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
    except Exception as exc:
        raise RuntimeError(
            'La lectura de rosbag2 requiere rosbag2_py, rclpy.serialization y rosidl_runtime_py en el entorno ROS 2.'
        ) from exc

    bag_uri = _normalize_bag_uri(bag_path)
    if not bag_uri.exists():
        raise FileNotFoundError(f'Rosbag no encontrado: {bag_path}')

    bag_uris = _discover_bag_uris(bag_uri)
    all_pairs: list[BagImagePair] = []
    global_index = 0
    skipped_bags: list[str] = []

    for current_bag_uri in bag_uris:
        try:
            bag_pairs = _load_single_rosbag_pairs(
                bag_uri=current_bag_uri,
                rgb_topic=rgb_topic,
                thermal_topic=thermal_topic,
                pair_tolerance_ms=pair_tolerance_ms,
                deserialize_modules=(rosbag2_py, deserialize_message, get_message),
            )
        except Exception as exc:
            LOGGER.warning('Saltando bag %s: %s', current_bag_uri, exc)
            skipped_bags.append(current_bag_uri.name)
            continue

        bag_name = current_bag_uri.name
        for pair in bag_pairs:
            all_pairs.append(
                BagImagePair(
                    name=f'{bag_name}__{global_index:06d}_{pair.stamp_ns}',
                    stamp_ns=pair.stamp_ns,
                    rgb_image=pair.rgb_image,
                    thermal_image=pair.thermal_image,
                )
            )
            global_index += 1

    if not all_pairs:
        bag_list = ', '.join(skipped_bags) if skipped_bags else str(bag_uri)
        raise ValueError(f'No se encontraron pares RGB/térmica válidos en los bags seleccionados: {bag_list}')

    pairs = all_pairs
    if sample_stride > 1:
        pairs = pairs[::sample_stride]
    if max_pairs > 0:
        pairs = pairs[:max_pairs]
    return pairs


def _load_single_rosbag_pairs(
    bag_uri: Path,
    rgb_topic: str,
    thermal_topic: str,
    pair_tolerance_ms: float,
    deserialize_modules,
) -> List[BagImagePair]:
    rosbag2_py, deserialize_message, get_message = deserialize_modules

    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=str(bag_uri), storage_id='sqlite3'),
        rosbag2_py.ConverterOptions(input_serialization_format='cdr', output_serialization_format='cdr'),
    )

    topics_and_types = reader.get_all_topics_and_types()
    topic_types = {topic.name: topic.type for topic in topics_and_types}
    missing_topics = [topic for topic in (rgb_topic, thermal_topic) if topic not in topic_types]
    if missing_topics:
        available_topics = ', '.join(sorted(topic_types))
        raise ValueError(
            f'Topics no encontrados en el bag {bag_uri.name}: {missing_topics}. Topics disponibles: {available_topics}'
        )

    rgb_message_type = get_message(topic_types[rgb_topic])
    thermal_message_type = get_message(topic_types[thermal_topic])
    rgb_messages: list[tuple[int, np.ndarray]] = []
    thermal_messages: list[tuple[int, np.ndarray]] = []

    while reader.has_next():
        topic_name, serialized_data, recorded_timestamp = reader.read_next()
        if topic_name == rgb_topic:
            msg = deserialize_message(serialized_data, rgb_message_type)
            stamp_ns = _stamp_to_ns(msg, recorded_timestamp)
            rgb_messages.append((stamp_ns, image_msg_to_numpy(msg)))
        elif topic_name == thermal_topic:
            msg = deserialize_message(serialized_data, thermal_message_type)
            stamp_ns = _stamp_to_ns(msg, recorded_timestamp)
            thermal_messages.append((stamp_ns, ensure_grayscale(image_msg_to_numpy(msg))))

    return _pair_by_timestamp(
        rgb_messages=rgb_messages,
        thermal_messages=thermal_messages,
        tolerance_ns=int(max(0.0, pair_tolerance_ms) * 1_000_000.0),
    )


def image_msg_to_numpy(msg) -> np.ndarray:
    encoding = str(msg.encoding).lower()
    height = int(msg.height)
    width = int(msg.width)
    step = int(msg.step)

    flat = np.frombuffer(msg.data, dtype=np.uint8)
    rows = flat.reshape((height, step))

    if encoding == 'mono8':
        return rows[:, :width].copy()
    if encoding in ('rgb8', 'bgr8'):
        image = rows[:, : width * 3].reshape((height, width, 3)).copy()
        if encoding == 'bgr8':
            return image[..., ::-1].copy()
        return image
    if encoding in ('rgba8', 'bgra8'):
        image = rows[:, : width * 4].reshape((height, width, 4)).copy()
        rgb = image[..., :3]
        if encoding == 'bgra8':
            return rgb[..., ::-1].copy()
        return rgb
    raise ValueError(f'Encoding no soportado en rosbag: {msg.encoding}')


def ensure_grayscale(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return np.ascontiguousarray(image)
    if image.ndim != 3 or image.shape[2] < 3:
        raise ValueError(f'Imagen térmica no válida: shape={image.shape}')
    grayscale = np.round(0.299 * image[..., 0] + 0.587 * image[..., 1] + 0.114 * image[..., 2])
    return np.ascontiguousarray(np.clip(grayscale, 0, 255).astype(np.uint8))


def rectify_stereo_pair(
    rgb_image: np.ndarray,
    thermal_image: np.ndarray,
    calibration: StereoCalibration,
    alpha: float = 0.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    try:
        import cv2
    except Exception as exc:
        raise RuntimeError('La rectificación estéreo requiere OpenCV Python (python3-opencv).') from exc

    if rgb_image.shape[:2] != thermal_image.shape[:2]:
        raise ValueError(
            f'La rectificación estéreo requiere imágenes del mismo tamaño. RGB={rgb_image.shape[:2]} térmica={thermal_image.shape[:2]}'
        )

    image_size = (int(rgb_image.shape[1]), int(rgb_image.shape[0]))
    rotation_rgb_to_thermal = calibration.thermal_to_rgb_rotation.T
    translation_rgb_to_thermal = -rotation_rgb_to_thermal @ calibration.thermal_to_rgb_translation_m.reshape(3, 1)

    rgb_rectification, thermal_rectification, rgb_projection, thermal_projection, _, _, _ = cv2.stereoRectify(
        cameraMatrix1=calibration.rgb_camera_matrix,
        distCoeffs1=calibration.rgb_distortion,
        cameraMatrix2=calibration.thermal_camera_matrix,
        distCoeffs2=calibration.thermal_distortion,
        imageSize=image_size,
        R=rotation_rgb_to_thermal,
        T=translation_rgb_to_thermal,
        flags=cv2.CALIB_ZERO_DISPARITY,
        alpha=alpha,
    )

    rgb_map_1, rgb_map_2 = cv2.initUndistortRectifyMap(
        calibration.rgb_camera_matrix,
        calibration.rgb_distortion,
        rgb_rectification,
        rgb_projection,
        image_size,
        cv2.CV_32FC1,
    )
    thermal_map_1, thermal_map_2 = cv2.initUndistortRectifyMap(
        calibration.thermal_camera_matrix,
        calibration.thermal_distortion,
        thermal_rectification,
        thermal_projection,
        image_size,
        cv2.CV_32FC1,
    )

    rgb_rectified = cv2.remap(rgb_image, rgb_map_1, rgb_map_2, interpolation=cv2.INTER_LINEAR)
    thermal_rectified = cv2.remap(thermal_image, thermal_map_1, thermal_map_2, interpolation=cv2.INTER_LINEAR)
    thermal_color = cv2.applyColorMap(thermal_rectified, cv2.COLORMAP_INFERNO)
    thermal_color = cv2.cvtColor(thermal_color, cv2.COLOR_BGR2RGB)
    return rgb_rectified, thermal_rectified, thermal_color


def build_stereo_calibration(
    rgb_camera_matrix: Sequence[float],
    rgb_distortion: Sequence[float],
    thermal_camera_matrix: Sequence[float],
    thermal_distortion: Sequence[float],
    thermal_to_rgb_rotation: Sequence[float],
    thermal_to_rgb_translation_m: Sequence[float],
) -> StereoCalibration:
    return StereoCalibration(
        rgb_camera_matrix=np.asarray(rgb_camera_matrix, dtype=np.float64).reshape(3, 3),
        rgb_distortion=np.asarray(rgb_distortion, dtype=np.float64).reshape(-1),
        thermal_camera_matrix=np.asarray(thermal_camera_matrix, dtype=np.float64).reshape(3, 3),
        thermal_distortion=np.asarray(thermal_distortion, dtype=np.float64).reshape(-1),
        thermal_to_rgb_rotation=np.asarray(thermal_to_rgb_rotation, dtype=np.float64).reshape(3, 3),
        thermal_to_rgb_translation_m=np.asarray(thermal_to_rgb_translation_m, dtype=np.float64).reshape(3),
    )


def _normalize_bag_uri(bag_path: Path) -> Path:
    if bag_path.is_dir():
        return bag_path
    if bag_path.name == 'metadata.yaml':
        return bag_path.parent
    if bag_path.suffix == '.db3':
        return bag_path.parent
    return bag_path


def _discover_bag_uris(bag_path: Path) -> List[Path]:
    if bag_path.is_dir() and (bag_path / 'metadata.yaml').is_file():
        return [bag_path]

    if bag_path.is_dir():
        candidates = [
            child for child in sorted(bag_path.iterdir())
            if child.is_dir() and (child / 'metadata.yaml').is_file()
        ]
        if candidates:
            return candidates

    return [bag_path]


def _stamp_to_ns(msg, recorded_timestamp: int) -> int:
    stamp = getattr(msg, 'header', None)
    if stamp is None:
        return int(recorded_timestamp)
    sec = int(getattr(msg.header.stamp, 'sec', 0))
    nanosec = int(getattr(msg.header.stamp, 'nanosec', 0))
    stamp_ns = sec * 1_000_000_000 + nanosec
    return stamp_ns if stamp_ns > 0 else int(recorded_timestamp)


def _pair_by_timestamp(
    rgb_messages: Iterable[tuple[int, np.ndarray]],
    thermal_messages: Iterable[tuple[int, np.ndarray]],
    tolerance_ns: int,
) -> List[BagImagePair]:
    rgb_sorted = sorted(rgb_messages, key=lambda item: item[0])
    thermal_sorted = sorted(thermal_messages, key=lambda item: item[0])
    pairs: list[BagImagePair] = []
    rgb_index = 0
    thermal_index = 0

    while rgb_index < len(rgb_sorted) and thermal_index < len(thermal_sorted):
        rgb_stamp_ns, rgb_image = rgb_sorted[rgb_index]
        thermal_stamp_ns, thermal_image = thermal_sorted[thermal_index]
        delta_ns = rgb_stamp_ns - thermal_stamp_ns

        if abs(delta_ns) <= tolerance_ns:
            pair_stamp_ns = max(rgb_stamp_ns, thermal_stamp_ns)
            pair_name = f'pair_{len(pairs):06d}_{pair_stamp_ns}'
            pairs.append(
                BagImagePair(
                    name=pair_name,
                    stamp_ns=pair_stamp_ns,
                    rgb_image=np.ascontiguousarray(rgb_image),
                    thermal_image=np.ascontiguousarray(thermal_image),
                )
            )
            rgb_index += 1
            thermal_index += 1
            continue

        if delta_ns < 0:
            rgb_index += 1
        else:
            thermal_index += 1

    return pairs