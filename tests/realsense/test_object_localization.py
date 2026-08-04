import numpy as np
import pytest

from vision.realsense.object_localization import (
    CameraPoint,
    MachinePoint,
    deproject_color_pixel,
    estimate_depth_m,
    project_target_to_writer_plane,
    transform_camera_to_machine,
)


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
