from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch


@dataclass
class TensorRTRuntimeConfig:
    engine_path: Path


class TensorRTRuntime:
    def __init__(self, config: TensorRTRuntimeConfig) -> None:
        self._config = config
        self._trt = None
        self._engine = None
        self._context = None
        self._binding_names: list[str] = []
        self._input_name = ''
        self._output_name = ''
        self._input_shape: tuple[int, ...] = ()
        self._output_shape: tuple[int, ...] = ()
        self._load_engine()

    def _load_engine(self) -> None:
        try:
            import tensorrt as trt
        except Exception as exc:
            raise RuntimeError(
                'No se pudo importar tensorrt. Este runtime requiere el modulo Python de TensorRT.'
            ) from exc

        engine_path = self._config.engine_path
        if not engine_path.is_file():
            raise FileNotFoundError(f'Engine TensorRT no encontrado: {engine_path}')

        logger = trt.Logger(trt.Logger.INFO)
        runtime = trt.Runtime(logger)
        engine_bytes = engine_path.read_bytes()
        engine = runtime.deserialize_cuda_engine(engine_bytes)
        if engine is None:
            raise RuntimeError(f'No se pudo deserializar el engine: {engine_path}')

        self._trt = trt
        self._engine = engine
        self._context = engine.create_execution_context()
        self._binding_names = [engine.get_tensor_name(index) for index in range(engine.num_io_tensors)]

        for tensor_name in self._binding_names:
            tensor_mode = engine.get_tensor_mode(tensor_name)
            tensor_shape = tuple(int(dim) for dim in engine.get_tensor_shape(tensor_name))
            if tensor_mode == trt.TensorIOMode.INPUT:
                self._input_name = tensor_name
                self._input_shape = tensor_shape
            elif tensor_mode == trt.TensorIOMode.OUTPUT:
                self._output_name = tensor_name
                self._output_shape = tensor_shape

        if not self._input_name or not self._output_name:
            raise RuntimeError('No se pudieron identificar los tensores de entrada/salida del engine TensorRT.')

    @property
    def binding_names(self) -> list[str]:
        return list(self._binding_names)

    @property
    def input_shape(self) -> tuple[int, ...]:
        return self._input_shape

    @property
    def output_shape(self) -> tuple[int, ...]:
        return self._output_shape

    def infer(self, input_tensor: np.ndarray) -> np.ndarray:
        if input_tensor.dtype != np.float32:
            input_tensor = input_tensor.astype(np.float32, copy=False)
        input_tensor = np.ascontiguousarray(input_tensor)

        if tuple(input_tensor.shape) != self._input_shape:
            raise ValueError(
                f'Forma de entrada no valida para TensorRT. Esperado {self._input_shape}, recibido {tuple(input_tensor.shape)}'
            )

        if not torch.cuda.is_available():
            raise RuntimeError('TensorRT runtime requiere CUDA disponible en el contenedor.')

        input_device = torch.from_numpy(input_tensor).to(device='cuda', dtype=torch.float32, non_blocking=True)
        output_device = torch.empty(self._output_shape, device='cuda', dtype=torch.float32)

        self._context.set_tensor_address(self._input_name, int(input_device.data_ptr()))
        self._context.set_tensor_address(self._output_name, int(output_device.data_ptr()))

        stream = torch.cuda.current_stream()
        ok = self._context.execute_async_v3(stream.cuda_stream)
        if not ok:
            raise RuntimeError('La ejecucion TensorRT fallo en execute_async_v3().')

        stream.synchronize()
        logits = output_device.cpu().numpy()
        prediction = np.argmax(logits, axis=1)
        return prediction.squeeze(0).astype(np.uint8)
