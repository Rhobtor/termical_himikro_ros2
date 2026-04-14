from __future__ import annotations

import importlib
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Tuple

import numpy as np
from PIL import Image
import torch


DEFAULT_PALETTE = np.array(
    [
        [0, 0, 0],
        [64, 0, 128],
        [64, 64, 0],
        [0, 128, 192],
        [0, 0, 192],
        [128, 128, 0],
        [64, 64, 128],
        [192, 128, 128],
        [192, 64, 0],
    ],
    dtype=np.uint8,
)


def _build_palette(num_classes: int) -> np.ndarray:
    if num_classes <= len(DEFAULT_PALETTE):
        return DEFAULT_PALETTE[:num_classes]

    extra = []
    for index in range(len(DEFAULT_PALETTE), num_classes):
        extra.append([
            (37 * index) % 256,
            (67 * index) % 256,
            (97 * index) % 256,
        ])
    return np.vstack([DEFAULT_PALETTE, np.array(extra, dtype=np.uint8)])


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def ensure_repo_on_path(repo_root: Path) -> None:
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)


def configure_torch_runtime(enable_cudnn_benchmark: bool = False) -> None:
    if hasattr(torch.backends, 'cudnn'):
        torch.backends.cudnn.benchmark = bool(enable_cudnn_benchmark)


def strip_module_prefix(state_dict: dict) -> OrderedDict:
    normalized = OrderedDict()
    for key, value in state_dict.items():
        normalized[key[7:] if key.startswith('module.') else key] = value
    return normalized


def load_model(
    repo_root: Path,
    checkpoint_path: Path,
    model_module: str,
    model_class: str,
    num_classes: int,
    device: torch.device,
) -> torch.nn.Module:
    ensure_repo_on_path(repo_root)
    module = importlib.import_module(model_module)
    model_ctor = getattr(module, model_class)

    try:
        model = model_ctor(num_classes, pretrained_backbone=False)
    except TypeError:
        model = model_ctor(num_classes)

    checkpoint = torch.load(checkpoint_path, map_location=device)
    if isinstance(checkpoint, dict) and 'model' in checkpoint:
        checkpoint = checkpoint['model']

    model.load_state_dict(strip_module_prefix(checkpoint), strict=True)
    model.to(device)
    model.eval()
    return model


def load_image_pair(
    rgb_path: Path,
    thermal_path: Path,
    image_size: Tuple[int, int],
) -> Tuple[np.ndarray, np.ndarray]:
    width, height = image_size

    rgb = Image.open(rgb_path).convert('RGB').resize((width, height), Image.BILINEAR)
    thermal = Image.open(thermal_path).convert('L').resize((width, height), Image.BILINEAR)
    return np.asarray(rgb, dtype=np.uint8), np.asarray(thermal, dtype=np.uint8)


def preprocess_pair(
    rgb_image: np.ndarray,
    thermal_image: np.ndarray,
    image_size: Tuple[int, int],
    rgb_scale: float,
    thermal_scale: float,
) -> Tuple[torch.Tensor, np.ndarray, np.ndarray]:
    width, height = image_size

    if rgb_image.shape[:2] != (height, width):
        rgb_image = np.asarray(
            Image.fromarray(rgb_image, mode='RGB').resize((width, height), Image.BILINEAR),
            dtype=np.uint8,
        )
    else:
        rgb_image = np.ascontiguousarray(rgb_image)

    if thermal_image.shape[:2] != (height, width):
        thermal_image = np.asarray(
            Image.fromarray(thermal_image, mode='L').resize((width, height), Image.BILINEAR),
            dtype=np.uint8,
        )
    else:
        thermal_image = np.ascontiguousarray(thermal_image)

    stacked = np.empty((4, height, width), dtype=np.float32)
    stacked[:3] = rgb_image.astype(np.float32).transpose(2, 0, 1)
    stacked[3] = thermal_image.astype(np.float32)

    if rgb_scale > 0.0:
        stacked[:3] /= rgb_scale
    if thermal_scale > 0.0:
        stacked[3] /= thermal_scale

    tensor = torch.from_numpy(stacked).unsqueeze(0)
    return tensor, rgb_image, thermal_image


def load_and_preprocess(
    rgb_path: Path,
    thermal_path: Path,
    image_size: Tuple[int, int],
    rgb_scale: float,
    thermal_scale: float,
) -> Tuple[torch.Tensor, np.ndarray]:
    rgb_image, thermal_image = load_image_pair(
        rgb_path=rgb_path,
        thermal_path=thermal_path,
        image_size=image_size,
    )
    tensor, rgb_resized, _ = preprocess_pair(
        rgb_image=rgb_image,
        thermal_image=thermal_image,
        image_size=image_size,
        rgb_scale=rgb_scale,
        thermal_scale=thermal_scale,
    )
    return tensor, rgb_resized


def predict_mask(
    model: torch.nn.Module,
    input_tensor: torch.Tensor,
    device: torch.device,
    use_amp: bool = False,
) -> np.ndarray:
    with torch.inference_mode():
        input_tensor = input_tensor.to(device=device, dtype=torch.float32, non_blocking=True)
        if use_amp and device.type == 'cuda':
            with torch.autocast(device_type='cuda', dtype=torch.float16):
                logits = model(input_tensor)
        else:
            logits = model(input_tensor)
        prediction = torch.argmax(logits, dim=1)
    return prediction.squeeze(0).cpu().numpy().astype(np.uint8)


def colorize_mask(mask: np.ndarray, palette: np.ndarray = DEFAULT_PALETTE) -> np.ndarray:
    if mask.max() >= len(palette):
        palette = _build_palette(int(mask.max()) + 1)
    return palette[mask]


def blend_overlay(rgb_image: np.ndarray, color_mask: np.ndarray, alpha: float = 0.45) -> np.ndarray:
    rgb_float = rgb_image.astype(np.float32)
    mask_float = color_mask.astype(np.float32)
    overlay = (1.0 - alpha) * rgb_float + alpha * mask_float
    return np.clip(overlay, 0, 255).astype(np.uint8)


def save_outputs(output_dir: Path, mask: np.ndarray, color_mask: np.ndarray, overlay: np.ndarray) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    Image.fromarray(mask, mode='L').save(output_dir / 'mask_indices.png')
    Image.fromarray(color_mask, mode='RGB').save(output_dir / 'mask_color.png')
    Image.fromarray(overlay, mode='RGB').save(output_dir / 'overlay.png')