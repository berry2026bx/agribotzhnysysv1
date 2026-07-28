import numpy as np
import pytest

from vision.realsense.aruco_reference_board import default_layout
from vision.realsense.live_red_target_dashboard import (
    ArucoReferenceTracker,
    reference_snapshot_state,
)


def project(matrix: np.ndarray, xy: tuple[float, float]) -> tuple[float, float]:
    value = matrix @ np.array([xy[0], xy[1], 1.0])
    return tuple((value[:2] / value[2]).tolist())


def all_markers() -> dict[int, np.ndarray]:
    layout = default_layout()
    machine_to_pixel = np.array(
        [[1.7, 0.15, 240.0], [0.12, 1.35, 130.0], [0.0004, -0.0003, 1.0]]
    )
    return {
        marker_id: np.asarray(
            [
                project(machine_to_pixel, point)
                for point in layout.marker_corner_machine_xy(marker_id)
            ]
        )
        for marker_id in range(6)
    }


def registration() -> dict[str, object]:
    return {"operator_confirmed": True, "motion_permission": "display_only"}


def test_tracker_requires_physical_registration() -> None:
    status = ArucoReferenceTracker(layout=default_layout(), registration=None).update(all_markers())

    assert status.state == "registration_required"
    assert status.matrix_pixel_to_machine is None


def test_tracker_collects_12_frames_then_drops_mapping_when_marker_is_missing() -> None:
    tracker = ArucoReferenceTracker(layout=default_layout(), registration=registration())
    markers = all_markers()

    for _ in range(11):
        status = tracker.update(markers)
        assert status.state == "collecting_reference_frames"
        assert status.matrix_pixel_to_machine is None

    ready = tracker.update(markers)
    assert ready.state == "ready"
    assert ready.matrix_pixel_to_machine is not None
    assert ready.validation is not None

    missing = dict(markers)
    missing.pop(5)
    lost = tracker.update(missing)
    assert lost.state == "reference_lost"
    assert lost.matrix_pixel_to_machine is None


def test_reference_state_is_always_display_only() -> None:
    state = reference_snapshot_state(
        state="calibration_rejected",
        detail="held-out maximum error 4.0 mm exceeds 3.0 mm",
        marker_corners={},
        validation=None,
    )

    assert state["motion_permission"] == "display_only"
    assert state["reference"]["state"] == "calibration_rejected"
    assert "machine_xy_mm" not in state


def test_tracker_rejects_non_finite_marker_corners() -> None:
    tracker = ArucoReferenceTracker(layout=default_layout(), registration=registration())
    invalid = all_markers()
    invalid[0][0, 0] = np.nan

    status = tracker.update(invalid)

    assert status.state == "reference_lost"
    assert status.matrix_pixel_to_machine is None
