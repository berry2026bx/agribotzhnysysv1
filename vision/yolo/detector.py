"""Lazy Ultralytics adapter for deterministic detection records."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable

import numpy as np


@dataclass(frozen=True)
class Detection:
    """One finite bounding box expressed in source-image pixel coordinates."""

    class_id: int
    class_name: str
    confidence: float
    xyxy: tuple[float, float, float, float]

    @property
    def center_uv(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.xyxy
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    @property
    def area(self) -> float:
        x1, y1, x2, y2 = self.xyxy
        return (x2 - x1) * (y2 - y1)


@dataclass(frozen=True)
class DetectorConfig:
    """User-selected model and bounded detection filtering policy."""

    model_path: str
    confidence: float = 0.5
    classes: frozenset[str] | None = None
    max_detections: int = 20

    def __post_init__(self) -> None:
        if not isinstance(self.model_path, str) or not self.model_path.strip():
            raise ValueError("model_path must be non-empty")
        if not math.isfinite(float(self.confidence)) or not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be within [0, 1]")
        if not isinstance(self.max_detections, int) or self.max_detections < 1:
            raise ValueError("max_detections must be positive")


class YoloDetector:
    """Run an Ultralytics detection model without making it a base dependency."""

    def __init__(self, config: DetectorConfig, *, model: Any | None = None) -> None:
        self.config = config
        if model is None:
            try:
                from ultralytics import YOLO
            except ImportError as exc:
                raise RuntimeError("yolo_dependency_missing: install torch and ultralytics") from exc
            model = YOLO(config.model_path)
        self._model = model

    def predict(self, rgb: np.ndarray) -> tuple[Detection, ...]:
        """Detect from a RealSense RGB array and return stable Python values."""

        image = np.asarray(rgb)
        if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
            raise ValueError("rgb must be a uint8 array with shape (height, width, 3)")
        bgr = np.ascontiguousarray(image[..., ::-1])
        results = self._model.predict(source=bgr, conf=float(self.config.confidence), verbose=False)
        if not results:
            return ()
        return parse_result(results[0], image.shape[1], image.shape[0], self.config)


def parse_result(result: Any, width: int, height: int, config: DetectorConfig) -> tuple[Detection, ...]:
    """Convert a result-like object into valid, sorted, bounded detections."""

    if width <= 0 or height <= 0:
        raise ValueError("image width and height must be positive")
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        return ()
    names = getattr(result, "names", {})
    xyxy = _as_numpy(getattr(boxes, "xyxy", None))
    conf = _as_numpy(getattr(boxes, "conf", None)).reshape(-1)
    cls = _as_numpy(getattr(boxes, "cls", None)).reshape(-1)
    detections: list[Detection] = []
    for index in range(min(len(xyxy), len(conf), len(cls))):
        coordinates = np.asarray(xyxy[index], dtype=float).reshape(-1)
        if coordinates.size != 4 or not np.all(np.isfinite(coordinates)):
            continue
        x1, y1, x2, y2 = coordinates.tolist()
        x1, x2 = sorted((max(0.0, min(float(width), x1)), max(0.0, min(float(width), x2))))
        y1, y2 = sorted((max(0.0, min(float(height), y1)), max(0.0, min(float(height), y2))))
        confidence = float(conf[index])
        raw_class = float(cls[index])
        if not math.isfinite(confidence) or confidence < config.confidence or not math.isfinite(raw_class):
            continue
        class_id = int(raw_class)
        class_name = str(names.get(class_id, class_id) if isinstance(names, dict) else class_id)
        if config.classes is not None and class_name not in config.classes:
            continue
        detection = Detection(class_id, class_name, confidence, (x1, y1, x2, y2))
        if detection.area > 0.0:
            detections.append(detection)
    detections.sort(key=lambda item: (-item.confidence, -item.area, item.class_id, item.xyxy))
    return tuple(detections[: config.max_detections])


def select_target(detections: Iterable[Detection], requested_class: str) -> Detection | None:
    """Choose the most confident valid instance of the requested class."""

    if not isinstance(requested_class, str) or not requested_class.strip():
        raise ValueError("requested_class must be non-empty")
    matching = [item for item in detections if item.class_name == requested_class.strip()]
    return min(matching, key=lambda item: (-item.confidence, -item.area, item.xyxy), default=None)


def _as_numpy(value: Any) -> np.ndarray:
    if value is None:
        return np.empty((0,), dtype=float)
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    return np.asarray(value)
