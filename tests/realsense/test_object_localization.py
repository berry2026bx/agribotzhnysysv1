import numpy as np
import pytest

from vision.realsense.object_localization import (
    CameraPoint,
    MachinePoint,
    deproject_color_pixel,
    estimate_depth_m,
    project_target_to_writer_plane,
    transform_camera_to_machine,
    transform_camera_to_writer,
)
from vision.realsense.aruco_reference_board import default_layout


def test_estimate_depth_uses_finite_positive_median() -> None:
    depth = np.array([[0.0, 1.0, np.nan], [2.0, 3.0, 4.0], [0.0, 5.0, 6.0]])
    assert estimate_depth_m(depth, 1, 1, radius=1) == pytest.approx(3.5)


def test_estimate_depth_rejects_zero_only() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        estimate_depth_m(np.zeros((3, 3)), 1, 1)


def test_deproject_converts_meters_to_mm() -> None:
    point = deproject_color_pixel(object(), 2.0, (10.0, 20.0), lambda _i, uv, z: (uv[0] * z, uv[1] * z, z))
    assert point == CameraPoint(20000.0, 40000.0, 2000.0)


def test_transform_and_plane_projection() -> None:
    point = transform_camera_to_machine(CameraPoint(1, 2, 3), np.eye(3), (10, 20, 30))
    assert point == MachinePoint(11, 22, 33)
    assert project_target_to_writer_plane(point, 0) == MachinePoint(11, 22, 0)


def test_inverse_board_pose_maps_camera_point_to_fixed_writer_p0_frame() -> None:
    # Board pose is board-to-camera: camera point (30, -10, 900) is board origin
    # when t=(30,-10,900). The layout maps its board origin to writer P0-relative XY.
    layout = default_layout()
    point = transform_camera_to_writer(
        CameraPoint(30, -10, 900),
        rotation=np.eye(3),
        translation=(30, -10, 900),
        layout=layout,
    )
    expected = layout.machine_xy_for_board((0.0, 0.0))
    assert point.x_mm == pytest.approx(expected[0])
    assert point.y_mm == pytest.approx(expected[1])
    assert point.z_mm == pytest.approx(0.0)
