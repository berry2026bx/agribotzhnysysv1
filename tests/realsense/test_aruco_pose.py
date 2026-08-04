import cv2
import numpy as np
import pytest

from vision.realsense.aruco_pose import estimate_board_pose, validate_board_pose
from vision.realsense.aruco_reference_board import default_layout


def _synthetic_corners():
    layout = default_layout()
    object_points = []
    for marker in layout.markers:
        object_points.extend((x, y, 0.0) for x, y in layout.marker_corner_board_xy(marker.identifier))
    object_points = np.asarray(object_points, dtype=np.float64)
    camera_matrix = np.array([[900.0, 0.0, 640.0], [0.0, 900.0, 360.0], [0.0, 0.0, 1.0]])
    dist = np.zeros(5)
    rvec = np.array([[0.08], [-0.12], [0.04]], dtype=np.float64)
    tvec = np.array([[20.0], [-15.0], [900.0]], dtype=np.float64)
    projected, _ = cv2.projectPoints(object_points, rvec, tvec, camera_matrix, dist)
    projected = projected.reshape(-1, 2)
    corners = {
        marker.identifier: projected[index * 4 : index * 4 + 4]
        for index, marker in enumerate(layout.markers)
    }
    return layout, camera_matrix, dist, rvec, tvec, corners


def test_estimate_board_pose_recovers_known_projection() -> None:
    layout, camera_matrix, dist, rvec, tvec, corners = _synthetic_corners()
    pose = estimate_board_pose(
        corners, camera_matrix, dist, layout, serial="231122070403", stream_size=(1280, 720)
    )
    assert pose.visible_ids == tuple(range(6))
    assert pose.translation == pytest.approx(tuple(tvec.reshape(-1)), abs=1e-3)
    assert pose.reprojection_error_px < 1e-5
    assert validate_board_pose(pose)


def test_estimate_board_pose_rejects_missing_marker() -> None:
    layout, camera_matrix, dist, _, _, corners = _synthetic_corners()
    corners.pop(5)
    with pytest.raises(ValueError, match="missing marker"):
        estimate_board_pose(corners, camera_matrix, dist, layout, serial="cam", stream_size=(1280, 720))


def test_validate_board_pose_rejects_large_reprojection_error() -> None:
    layout, camera_matrix, dist, _, _, corners = _synthetic_corners()
    corners[0] = corners[0] + 20.0
    with pytest.raises(ValueError, match="reprojection"):
        estimate_board_pose(corners, camera_matrix, dist, layout, serial="cam", stream_size=(1280, 720))
