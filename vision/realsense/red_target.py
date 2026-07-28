"""Display-only red planar-target detection and coordinate observation."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from .camera_probe import find_valid_depth_pixel
from .plane_mapping import PlaneMappingError, predict_machine_xy


class RedTargetError(ValueError):
    """Raised when a target frame cannot support a display-only observation."""


@dataclass(frozen=True)
class RedTargetConfig:
    min_red: int = 150
    min_red_advantage: int = 80
    min_area_px: int = 40
    min_fill_ratio: float = 0.55
    max_aspect_ratio: float = 4.0


@dataclass(frozen=True)
class RedTarget:
    center_uv: tuple[float, float]
    area_px: int
    bbox_uvwh: tuple[int, int, int, int]
    fill_ratio: float


@dataclass(frozen=True)
class TargetObservation:
    target_center_uv: tuple[float, float]
    depth_sample_uv: tuple[int, int]
    depth_m: float
    camera_xyz_m: tuple[float, float, float]
    machine_xy_mm: tuple[float, float]


def find_red_target(
    rgb: np.ndarray, config: RedTargetConfig | None = None
) -> RedTarget | None:
    """Return the largest filled, approximately circular saturated-red component."""
    normalized_config = config or RedTargetConfig()
    _validate_config(normalized_config)
    image = np.asarray(rgb)
    if image.ndim != 3 or image.shape[2] != 3:
        raise RedTargetError("RGB image must have shape (height, width, 3)")
    if image.shape[0] <= 0 or image.shape[1] <= 0:
        raise RedTargetError("RGB image dimensions must be positive")

    channels = image.astype(np.int16, copy=False)
    red, green, blue = channels[:, :, 0], channels[:, :, 1], channels[:, :, 2]
    mask = (
        (red >= normalized_config.min_red)
        & ((red - green) >= normalized_config.min_red_advantage)
        & ((red - blue) >= normalized_config.min_red_advantage)
    )
    candidates = _red_component_candidates(mask, normalized_config)
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: candidate.area_px)


def observe_target(
    target: RedTarget,
    *,
    depth_frame: Any,
    color_intrinsics: Any,
    deproject: Callable[[Any, list[int], float], Sequence[float]],
    pixel_to_machine: np.ndarray,
    width: int,
    height: int,
    depth_sample_radius: int = 5,
) -> TargetObservation:
    """Build a metric camera and display-only machine-plane observation."""
    if not isinstance(target, RedTarget):
        raise RedTargetError("target must be a RedTarget")
    if width <= 0 or height <= 0:
        raise RedTargetError("image dimensions must be positive")
    target_u, target_v = target.center_uv
    _require_finite(target_u, "target center u")
    _require_finite(target_v, "target center v")
    requested_center = (int(round(target_u)), int(round(target_v)))
    try:
        sample_u, sample_v, depth_m = find_valid_depth_pixel(
            depth_frame,
            center=requested_center,
            width=width,
            height=height,
            radius=depth_sample_radius,
        )
    except Exception as exc:
        raise RedTargetError(f"no valid aligned depth for red target: {exc}") from exc

    try:
        camera_point = tuple(
            float(value) for value in deproject(color_intrinsics, [sample_u, sample_v], depth_m)
        )
    except Exception as exc:
        raise RedTargetError("camera deprojection failed") from exc
    if len(camera_point) != 3 or not all(math.isfinite(value) for value in camera_point):
        raise RedTargetError(f"invalid camera coordinate: {camera_point!r}")

    try:
        machine_xy = predict_machine_xy(pixel_to_machine, target.center_uv)
    except PlaneMappingError as exc:
        raise RedTargetError(f"invalid planar mapping: {exc}") from exc
    return TargetObservation(
        target_center_uv=target.center_uv,
        depth_sample_uv=(sample_u, sample_v),
        depth_m=float(depth_m),
        camera_xyz_m=camera_point,
        machine_xy_mm=machine_xy,
    )


def _red_component_candidates(mask: np.ndarray, config: RedTargetConfig) -> list[RedTarget]:
    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    candidates: list[RedTarget] = []
    rows, columns = np.nonzero(mask)
    for start_v, start_u in zip(rows.tolist(), columns.tolist()):
        if visited[start_v, start_u]:
            continue
        pixels = _component_pixels(mask, visited, start_u, start_v, width, height)
        candidate = _as_red_target(pixels, config)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _component_pixels(
    mask: np.ndarray,
    visited: np.ndarray,
    start_u: int,
    start_v: int,
    width: int,
    height: int,
) -> list[tuple[int, int]]:
    stack = [(start_u, start_v)]
    visited[start_v, start_u] = True
    pixels: list[tuple[int, int]] = []
    while stack:
        u, v = stack.pop()
        pixels.append((u, v))
        for neighbor_v in range(max(0, v - 1), min(height, v + 2)):
            for neighbor_u in range(max(0, u - 1), min(width, u + 2)):
                if not visited[neighbor_v, neighbor_u] and mask[neighbor_v, neighbor_u]:
                    visited[neighbor_v, neighbor_u] = True
                    stack.append((neighbor_u, neighbor_v))
    return pixels


def _as_red_target(
    pixels: list[tuple[int, int]], config: RedTargetConfig
) -> RedTarget | None:
    area_px = len(pixels)
    if area_px < config.min_area_px:
        return None
    coordinates = np.asarray(pixels, dtype=float)
    min_u, min_v = coordinates.min(axis=0).astype(int).tolist()
    max_u, max_v = coordinates.max(axis=0).astype(int).tolist()
    bbox_width = max_u - min_u + 1
    bbox_height = max_v - min_v + 1
    aspect_ratio = max(bbox_width, bbox_height) / min(bbox_width, bbox_height)
    fill_ratio = area_px / float(bbox_width * bbox_height)
    if aspect_ratio > config.max_aspect_ratio or fill_ratio < config.min_fill_ratio:
        return None
    center_u, center_v = coordinates.mean(axis=0).tolist()
    return RedTarget(
        center_uv=(float(center_u), float(center_v)),
        area_px=area_px,
        bbox_uvwh=(min_u, min_v, bbox_width, bbox_height),
        fill_ratio=float(fill_ratio),
    )


def _validate_config(config: RedTargetConfig) -> None:
    for name, value in (
        ("min_red", config.min_red),
        ("min_red_advantage", config.min_red_advantage),
        ("min_area_px", config.min_area_px),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise RedTargetError(f"{name} must be a positive integer")
    for name, value in (
        ("min_fill_ratio", config.min_fill_ratio),
        ("max_aspect_ratio", config.max_aspect_ratio),
    ):
        _require_finite(value, name)
    if not 0.0 < config.min_fill_ratio <= 1.0:
        raise RedTargetError("min_fill_ratio must be in (0, 1]")
    if config.max_aspect_ratio < 1.0:
        raise RedTargetError("max_aspect_ratio must be at least one")


def _require_finite(value: object, label: str) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise RedTargetError(f"{label} must be finite") from exc
    if not math.isfinite(normalized):
        raise RedTargetError(f"{label} must be finite")
    return normalized
