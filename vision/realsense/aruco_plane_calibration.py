"""Display-only camera-A plane calibration from a fixed A4 ArUco reference board."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import AbstractSet, Any

import cv2
import numpy as np

from .aruco_reference_board import (
    ARUCO_DICTIONARY_NAME,
    FIT_MARKER_IDS,
    VALIDATION_MARKER_IDS,
    ArucoBoardLayout,
)
from .plane_mapping import CalibrationPoint, PlaneMappingError, fit_pixel_to_machine, predict_machine_xy


COLOR_FRAME_SIZE = (640, 480)
REQUIRED_COMPLETE_FRAMES = 12


class SessionCalibrationError(ValueError):
    """Raised when a reference-board session cannot support display-only mapping."""


@dataclass(frozen=True)
class ArucoSessionResult:
    """A validated display-only mapping plus its immutable session record."""

    record: dict[str, Any]
    matrix_pixel_to_machine: np.ndarray
    median_corners_uv: dict[int, np.ndarray]


def detect_marker_corners(rgb: np.ndarray, layout: ArucoBoardLayout) -> dict[int, np.ndarray]:
    """Return expected marker IDs with clockwise finite ``(4, 2)`` RGB-pixel corners."""
    image = np.asarray(rgb)
    if image.ndim != 3 or image.shape[2] != 3:
        raise SessionCalibrationError("ArUco detection requires an RGB image")
    if image.dtype != np.uint8:
        raise SessionCalibrationError("ArUco detection requires uint8 RGB pixels")
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, ARUCO_DICTIONARY_NAME))
    grayscale = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    corners, identifiers, _ = cv2.aruco.detectMarkers(grayscale, dictionary)
    if identifiers is None:
        return {}

    expected_ids = {marker.identifier for marker in layout.markers}
    result: dict[int, np.ndarray] = {}
    for identifier, corner_set in zip(identifiers.flatten().tolist(), corners, strict=True):
        marker_id = int(identifier)
        if marker_id in expected_ids:
            result[marker_id] = _normalized_corners(corner_set, f"marker {marker_id}")
    return dict(sorted(result.items()))


def median_marker_corners(
    complete_frames: Sequence[Mapping[int, np.ndarray]], required_ids: AbstractSet[int]
) -> dict[int, np.ndarray]:
    """Median each required marker corner independently across complete frames."""
    frames = list(complete_frames)
    if not frames:
        raise SessionCalibrationError("at least one complete frame is required")
    medians: dict[int, np.ndarray] = {}
    for marker_id in sorted(required_ids):
        corner_samples: list[np.ndarray] = []
        for frame_index, frame in enumerate(frames):
            if marker_id not in frame:
                raise SessionCalibrationError(
                    f"complete frame {frame_index} is missing marker id {marker_id}"
                )
            corner_samples.append(
                _normalized_corners(frame[marker_id], f"frame {frame_index} marker {marker_id}")
            )
        medians[marker_id] = np.median(np.stack(corner_samples, axis=0), axis=0)
    return medians


def build_aruco_session_record(
    *,
    serial: str,
    frame_size: tuple[int, int],
    layout: ArucoBoardLayout,
    complete_frames: Sequence[Mapping[int, np.ndarray]],
    captured_at_utc: str,
    mean_error_limit_mm: float = 1.5,
    max_error_limit_mm: float = 3.0,
) -> ArucoSessionResult:
    """Fit four marker IDs and validate two held-out IDs without motion authority."""
    _validate_serial(serial)
    _validate_frame_size(frame_size)
    _validate_timestamp(captured_at_utc)
    _validate_limit(mean_error_limit_mm, "mean_error_limit_mm")
    _validate_limit(max_error_limit_mm, "max_error_limit_mm")
    frames = list(complete_frames)
    required_ids = FIT_MARKER_IDS | VALIDATION_MARKER_IDS
    if len(frames) != REQUIRED_COMPLETE_FRAMES:
        raise SessionCalibrationError(f"exactly {REQUIRED_COMPLETE_FRAMES} complete frames are required")
    _validate_complete_frames(frames, required_ids)

    medians = median_marker_corners(frames, required_ids)
    fit_points = _calibration_points(layout, medians, FIT_MARKER_IDS)
    validation_points = _calibration_points(layout, medians, VALIDATION_MARKER_IDS)
    try:
        matrix = fit_pixel_to_machine(fit_points)
    except PlaneMappingError as exc:
        raise SessionCalibrationError(f"cannot fit ArUco plane mapping: {exc}") from exc

    validation_records: list[dict[str, Any]] = []
    errors: list[float] = []
    for point in validation_points:
        try:
            predicted_x, predicted_y = predict_machine_xy(matrix, point.pixel_uv)
        except PlaneMappingError as exc:
            raise SessionCalibrationError(f"cannot predict held-out marker corner: {exc}") from exc
        expected_x, expected_y = point.machine_xy_mm
        error_mm = math.hypot(predicted_x - expected_x, predicted_y - expected_y)
        errors.append(error_mm)
        validation_records.append(
            {
                "id": point.identifier,
                "pixel_uv": {"u": point.pixel_uv[0], "v": point.pixel_uv[1]},
                "expected_machine_xy_mm": {"x": expected_x, "y": expected_y},
                "predicted_machine_xy_mm": {"x": predicted_x, "y": predicted_y},
                "error_mm": error_mm,
            }
        )
    mean_error_mm = float(np.mean(errors))
    max_error_mm = float(np.max(errors))
    if mean_error_mm > mean_error_limit_mm or max_error_mm > max_error_limit_mm:
        raise SessionCalibrationError(
            "held-out marker error exceeds display-only limits: "
            f"mean={mean_error_mm:.3f} mm, max={max_error_mm:.3f} mm"
        )

    return ArucoSessionResult(
        record={
            "schema_version": 1,
            "captured_at_utc": captured_at_utc.strip(),
            "camera": {"serial": serial.strip()},
            "stream": {"color_width": frame_size[0], "color_height": frame_size[1], "frame_rate": 30},
            "board": {"revision": layout.revision, "dictionary": ARUCO_DICTIONARY_NAME},
            "fit_marker_ids": sorted(FIT_MARKER_IDS),
            "validation_marker_ids": sorted(VALIDATION_MARKER_IDS),
            "median_marker_corners_uv": {
                str(marker_id): _corner_records(corners) for marker_id, corners in medians.items()
            },
            "fit_points": [_point_record(point) for point in fit_points],
            "matrix_pixel_to_machine": matrix.tolist(),
            "validation": {
                "count": len(validation_records),
                "mean_error_mm": mean_error_mm,
                "max_error_mm": max_error_mm,
                "mean_error_limit_mm": float(mean_error_limit_mm),
                "max_error_limit_mm": float(max_error_limit_mm),
                "points": validation_records,
            },
            "motion_permission": "display_only",
            "limitations": [
                "The mapping is valid only while the fixed A4 reference board is visible.",
                "This artifact does not authorize GRBL motion.",
            ],
        },
        matrix_pixel_to_machine=matrix,
        median_corners_uv=medians,
    )


def _validate_complete_frames(
    frames: Sequence[Mapping[int, np.ndarray]], required_ids: AbstractSet[int]
) -> None:
    for frame_index, frame in enumerate(frames):
        if not isinstance(frame, Mapping):
            raise SessionCalibrationError(f"complete frame {frame_index} must be a marker mapping")
        missing = sorted(required_ids - set(frame))
        if missing:
            raise SessionCalibrationError(
                f"complete frame {frame_index} is missing marker ids {missing}"
            )
        for marker_id in required_ids:
            _normalized_corners(frame[marker_id], f"frame {frame_index} marker {marker_id}")


def _calibration_points(
    layout: ArucoBoardLayout, medians: Mapping[int, np.ndarray], marker_ids: AbstractSet[int]
) -> list[CalibrationPoint]:
    points: list[CalibrationPoint] = []
    for marker_id in sorted(marker_ids):
        for corner_index, (pixel_uv, machine_xy_mm) in enumerate(
            zip(
                medians[marker_id],
                layout.marker_corner_machine_xy(marker_id),
                strict=True,
            )
        ):
            points.append(
                CalibrationPoint(
                    f"marker-{marker_id}-corner-{corner_index}",
                    (float(pixel_uv[0]), float(pixel_uv[1])),
                    machine_xy_mm,
                )
            )
    return points


def _normalized_corners(value: object, label: str) -> np.ndarray:
    corners = np.asarray(value, dtype=float)
    if corners.shape == (1, 4, 2):
        corners = corners[0]
    if corners.shape != (4, 2) or not np.all(np.isfinite(corners)):
        raise SessionCalibrationError(f"{label} must be a finite (4, 2) corner array")
    return corners


def _validate_serial(value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise SessionCalibrationError("camera serial must be a non-empty string")


def _validate_frame_size(frame_size: object) -> None:
    if frame_size != COLOR_FRAME_SIZE:
        raise SessionCalibrationError("ArUco reference sessions require a 640x480 RGB stream")


def _validate_timestamp(value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise SessionCalibrationError("captured_at_utc must be a non-empty string")


def _validate_limit(value: object, label: str) -> None:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SessionCalibrationError(f"{label} must be a positive finite number") from exc
    if not math.isfinite(number) or number <= 0.0:
        raise SessionCalibrationError(f"{label} must be a positive finite number")


def _corner_records(corners: np.ndarray) -> list[dict[str, float]]:
    return [{"u": float(corner[0]), "v": float(corner[1])} for corner in corners]


def _point_record(point: CalibrationPoint) -> dict[str, object]:
    return {
        "id": point.identifier,
        "pixel_uv": {"u": point.pixel_uv[0], "v": point.pixel_uv[1]},
        "machine_xy_mm": {"x": point.machine_xy_mm[0], "y": point.machine_xy_mm[1]},
    }
