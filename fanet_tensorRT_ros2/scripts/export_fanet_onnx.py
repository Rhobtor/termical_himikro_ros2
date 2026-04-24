#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import torch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Exporta FEANet desde PyTorch a ONNX para TensorRT.')
    parser.add_argument('--repo-root', required=True, help='Ruta al repo CPGFANet original.')
    parser.add_argument('--checkpoint', required=True, help='Ruta al checkpoint .pth.')
    parser.add_argument('--output', required=True, help='Ruta de salida del archivo .onnx.')
    parser.add_argument('--model-module', default='model.CrissCrossAttention_dual_2_sinINF')
    parser.add_argument('--model-class', default='FEANet')
    parser.add_argument('--num-classes', type=int, default=12)
    parser.add_argument('--input-width', type=int, default=448)
    parser.add_argument('--input-height', type=int, default=352)
    parser.add_argument('--opset', type=int, default=17)
    parser.add_argument('--device', default='cpu', choices=['cpu', 'cuda'])
    return parser.parse_args()


def ensure_repo_on_path(repo_root: Path) -> None:
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)


def strip_module_prefix(state_dict: dict) -> dict:
    normalized = {}
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
    module = __import__(model_module, fromlist=[model_class])
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


def main() -> None:
    args = parse_args()

    repo_root = Path(args.repo_root).resolve()
    checkpoint_path = Path(args.checkpoint).resolve()
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.device == 'cuda' and not torch.cuda.is_available():
        raise RuntimeError('Se solicito CUDA para exportar ONNX, pero torch.cuda no esta disponible.')

    device = torch.device(args.device)
    model = load_model(
        repo_root=repo_root,
        checkpoint_path=checkpoint_path,
        model_module=args.model_module,
        model_class=args.model_class,
        num_classes=int(args.num_classes),
        device=device,
    )

    dummy_input = torch.randn(
        1,
        4,
        int(args.input_height),
        int(args.input_width),
        device=device,
        dtype=torch.float32,
    )

    with torch.inference_mode():
        torch.onnx.export(
            model,
            dummy_input,
            str(output_path),
            export_params=True,
            opset_version=int(args.opset),
            do_constant_folding=True,
            input_names=['input'],
            output_names=['logits'],
            dynamic_axes=None,
        )

    print(f'ONNX exportado en: {output_path}')


if __name__ == '__main__':
    main()