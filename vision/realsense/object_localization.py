"""Depth sampling and pure camera-to-machine transforms for elevated targets."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Sequence

import numpy as np

from .aruco_reference_board import ArucoBoardLayout


@dataclass(frozen=True)
class CameraPoint:
    x_mm: float
    y_mm: float
    z_mm: float


@dataclass(frozen=True)
class MachinePoint:
    x_mm: float
    y_mm: float
    z_mm: float


def estimate_depth_m(depth_frame: object, u: int, v: int, radius: int = 2) -> float:
    """Use a local finite-positive median rather than one fragile center pixel."""

    if not isinstance(radius, int) or radius < 0:
        raise ValueError("radius must be a non-negative integer")
    if hasattr(depth_frame, "get_distance"):
        values: list[float] = []
        for row in range(v - radius, v + radius + 1):
            for column in range(u - radius, u + radius + 1):
                try:
                    values.append(float(depth_frame.get_distance(column, row)))
                except (IndexError, RuntimeError, TypeError, ValueError):
                    continue
    else:
        array = np.asarray(depth_frame, dtype=float)
        if array.ndim != 2:
            raise ValueError("depth_frame must be a 2-D array or RealSense depth frame")
        height, width = array.shape
        values = array[max(0, v - radius) : min(height, v + radius + 1), max(0, u - radius) : min(width, u + radius + 1)].reshape(-1).tolist()
    samples = np.asarray([sample for sample in values if math.isfinite(sample) and sample > 0.0], dtype=float)
    if samples.size == 0:
        raise ValueError("depth must be finite and greater than zero")
    return float(np.median(samples))


def deproject_color_pixel(
    color_intrinsics: object,
    depth_m: float,
    uv: tuple[float, float],
    deproject: Callable[[object, Sequence[float], float], Sequence[float]],
) -> CameraPoint:
    """Use RealSense deprojection and make millimetres explicit at this boundary."""

    depth = float(depth_m)
    if not math.isfinite(depth) or depth <= 0.0:
        raise ValueError("depth must be finite and greater than zero")
    u, v = float(uv[0]), float(uv[1])
    if not math.isfinite(u) or not math.isfinite(v):
        raise ValueError("pixel coordinates must be finite")
    point_m = np.asarray(deproject(color_intrinsics, (u, v), depth), dtype=float).reshape(-1)
    if point_m.size != 3 or not np.all(np.isfinite(point_m)):
        raise ValueError("deprojected point must contain three finite values")
    return CameraPoint(*(float(item) * 1000.0 for item in point_m))


def transform_camera_to_machine(
    camera_point: CameraPoint,
    rotation: Sequence[Sequence[float]],
    translation: Sequence[float],
) -> MachinePoint:
    """Apply the checked 3-D rigid transform in millimetres."""

    matrix = np.asarray(rotation, dtype=float)
    offset = np.asarray(translation, dtype=float).reshape(-1)
    point = np.asarray((camera_point.x_mm, camera_point.y_mm, camera_point.z_mm), dtype=float)
    if matrix.shape != (3, 3) or offset.size != 3 or not np.all(np.isfinite(matrix)) or not np.all(np.isfinite(offset)):
        raise ValueError("rotation and translation must be finite 3-D transform values")
    result = matrix @ point + offset
    if not np.all(np.isfinite(result)):
        raise ValueError("machine point must be finite")
    return MachinePoint(*[float(item) for item in result])


def project_target_to_writer_plane(machine_point: MachinePoint, plane_z_mm: float) -> MachinePoint:
    """Report target height separately while keeping an XY plane projection explicit."""

    plane_z = float(plane_z_mm)
    if not math.isfinite(plane_z):
        raise ValueError("plane_z_mm must be finite")
    return MachinePoint(machine_point.x_mm, machine_point.y_mm, plane_z)


def transform_camera_to_writer(
    camera_point: CameraPoint,
    rotation: Sequence[Sequence[float]],
    translation: Sequence[float],
    *,
    layout: ArucoBoardLayout,
) -> MachinePoint:
    """Invert the board-to-camera pose and map board XY through fixed P0."""

    matrix = np.asarray(rotation, dtype=float)
    offset = np.asarray(translation, dtype=float).reshape(-1)
    camera = np.asarray((camera_point.x_mm, camera_point.y_mm, camera_point.z_mm), dtype=float)
    if matrix.shape != (3, 3) or offset.size != 3 or not np.all(np.isfinite(matrix)) or not np.all(np.isfinite(offset)):
        raise ValueError("rotation and translation must be finite 3-D transform values")
    board = matrix.T @ (camera - offset)
    if not np.all(np.isfinite(board)):
        raise ValueError("board point must be finite")
    x_mm, y_mm = layout.machine_xy_for_board((float(board[0]), float(board[1])))
    return MachinePoint(x_mm, y_mm, float(board[2]))
