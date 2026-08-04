"""Validated six-marker board pose estimation for the YOLO 3-D path."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Mapping, Sequence

import cv2
import numpy as np

from .aruco_reference_board import ArucoBoardLayout


@dataclass(frozen=True)
class BoardPose:
    rotation: tuple[tuple[float, float, float], ...]
    translation: tuple[float, float, float]
    reprojection_error_px: float
    visible_ids: tuple[int, ...]
    serial: str
    stream_size: tuple[int, int]
    captured_at_utc: str
    board_revision: str

    def record(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "captured_at_utc": self.captured_at_utc,
            "camera": {"serial": self.serial},
            "stream": {"width": self.stream_size[0], "height": self.stream_size[1]},
            "board": {"revision": self.board_revision},
            "visible_ids": list(self.visible_ids),
            "rotation": [list(row) for row in self.rotation],
            "translation_mm": list(self.translation),
            "reprojection_error_px": self.reprojection_error_px,
        }


def estimate_board_pose(
    corners_by_id: Mapping[int, np.ndarray],
    camera_matrix: np.ndarray,
    dist_coeffs: np.ndarray,
    layout: ArucoBoardLayout,
    *,
    serial: str,
    stream_size: tuple[int, int],
    max_reprojection_error_px: float = 2.0,
) -> BoardPose:
    """Solve the board pose from all six known marker corners."""

    expected_ids = tuple(marker.identifier for marker in layout.markers)
    missing = [marker_id for marker_id in expected_ids if marker_id not in corners_by_id]
    if missing:
        raise ValueError(f"missing marker ids: {missing}")
    if not isinstance(serial, str) or not serial.strip():
        raise ValueError("camera serial must be non-empty")
    if len(stream_size) != 2 or any(int(item) <= 0 for item in stream_size):
        raise ValueError("stream_size must contain positive width and height")
    object_points: list[tuple[float, float, float]] = []
    image_points: list[tuple[float, float]] = []
    for marker_id in expected_ids:
        corners = np.asarray(corners_by_id[marker_id], dtype=np.float64)
        if corners.shape == (1, 4, 2):
            corners = corners[0]
        if corners.shape != (4, 2) or not np.all(np.isfinite(corners)):
            raise ValueError(f"marker {marker_id} corners must be finite shape (4, 2)")
        object_points.extend((x, y, 0.0) for x, y in layout.marker_corner_board_xy(marker_id))
        image_points.extend((float(point[0]), float(point[1])) for point in corners)
    object_array = np.asarray(object_points, dtype=np.float64)
    image_array = np.asarray(image_points, dtype=np.float64)
    camera = np.asarray(camera_matrix, dtype=np.float64)
    distortion = np.asarray(dist_coeffs, dtype=np.float64)
    if camera.shape != (3, 3) or not np.all(np.isfinite(camera)) or not np.all(np.isfinite(distortion)):
        raise ValueError("camera calibration must be finite 3x3 intrinsics and distortion")
    success, rvec, tvec = cv2.solvePnP(
        object_array,
        image_array,
        camera,
        distortion,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not success or not np.all(np.isfinite(rvec)) or not np.all(np.isfinite(tvec)):
        raise ValueError("board pose is non-finite")
    rotation, _ = cv2.Rodrigues(rvec)
    projected, _ = cv2.projectPoints(object_array, rvec, tvec, camera, distortion)
    residuals = np.linalg.norm(projected.reshape(-1, 2) - image_array, axis=1)
    reprojection_error = float(np.sqrt(np.mean(residuals * residuals)))
    if not math.isfinite(reprojection_error) or reprojection_error > float(max_reprojection_error_px):
        raise ValueError(
            f"board reprojection error {reprojection_error:.3f} px exceeds {max_reprojection_error_px:g} px"
        )
    return BoardPose(
        rotation=tuple(tuple(float(value) for value in row) for row in rotation),
        translation=tuple(float(value) for value in tvec.reshape(-1)),
        reprojection_error_px=reprojection_error,
        visible_ids=expected_ids,
        serial=serial.strip(),
        stream_size=(int(stream_size[0]), int(stream_size[1])),
        captured_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        board_revision=layout.revision,
    )


def validate_board_pose(
    pose: BoardPose,
    *,
    previous_pose: BoardPose | None = None,
    max_reprojection_error_px: float = 2.0,
    max_translation_change_mm: float = 8.0,
) -> bool:
    """Validate current quality and reject sudden board movement."""

    if not math.isfinite(pose.reprojection_error_px) or pose.reprojection_error_px > max_reprojection_error_px:
        raise ValueError("board reprojection error is invalid")
    if previous_pose is not None:
        change = np.linalg.norm(np.asarray(pose.translation) - np.asarray(previous_pose.translation))
        if not math.isfinite(float(change)) or change > max_translation_change_mm:
            raise ValueError("board translation changed beyond the validation limit")
    return True
