import math

import numpy as np
import pytest

from vision.realsense.plane_mapping import (
    CalibrationPoint,
    PlaneMappingError,
    build_calibration_record,
    fit_pixel_to_machine,
    predict_machine_xy,
)


def project(matrix: np.ndarray, machine_xy_mm: tuple[float, float]) -> tuple[float, float]:
    x, y = machine_xy_mm
    homogeneous = matrix @ np.array([x, y, 1.0])
    return tuple((homogeneous[:2] / homogeneous[2]).tolist())


def make_points() -> tuple[list[CalibrationPoint], CalibrationPoint]:
    machine_to_pixel = np.array(
        [
            [1.3, 0.2, 250.0],
            [0.1, 1.1, 120.0],
            [0.0008, -0.0004, 1.0],
        ]
    )
    fit_xy = [(0.0, 0.0), (80.0, 0.0), (80.0, 60.0), (0.0, 60.0), (35.0, 20.0)]
    fit_points = [
        CalibrationPoint(f"fit-{index}", project(machine_to_pixel, xy), xy)
        for index, xy in enumerate(fit_xy)
    ]
    validation_xy = (25.0, 45.0)
    validation_point = CalibrationPoint(
        "validation-center", project(machine_to_pixel, validation_xy), validation_xy
    )
    return fit_points, validation_point


def test_fit_predicts_a_held_out_projective_point() -> None:
    fit_points, validation_point = make_points()

    matrix = fit_pixel_to_machine(fit_points)

    assert predict_machine_xy(matrix, validation_point.pixel_uv) == pytest.approx(
        validation_point.machine_xy_mm, abs=1e-8
    )


def test_fit_rejects_fewer_than_four_points() -> None:
    fit_points, _ = make_points()

    with pytest.raises(PlaneMappingError, match="at least four"):
        fit_pixel_to_machine(fit_points[:3])


def test_fit_rejects_collinear_pixels() -> None:
    points = [
        CalibrationPoint(str(index), (float(index), float(index)), (float(index), 0.0))
        for index in range(4)
    ]

    with pytest.raises(PlaneMappingError, match="degenerate"):
        fit_pixel_to_machine(points)


def test_calibration_record_reports_validation_error_and_is_display_only() -> None:
    fit_points, validation_point = make_points()

    record = build_calibration_record(
        "231122070403", fit_points, [validation_point], captured_at_utc="2026-07-28T00:00:00Z"
    )

    assert record["motion_permission"] == "display_only"
    assert record["validation"]["count"] == 1
    assert record["validation"]["max_error_mm"] == pytest.approx(0.0, abs=1e-8)
    assert math.isfinite(record["validation"]["mean_error_mm"])
