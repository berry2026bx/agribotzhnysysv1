import cv2
import numpy as np
import pytest

from vision.realsense import aruco_plane_calibration
from vision.realsense.aruco_plane_calibration import (
    SessionCalibrationError,
    build_aruco_session_record,
    detect_marker_corners,
    median_marker_corners,
)
from vision.realsense.aruco_reference_board import ARUCO_DICTIONARY_NAME, default_layout


def project(matrix: np.ndarray, xy: tuple[float, float]) -> tuple[float, float]:
    result = matrix @ np.array([xy[0], xy[1], 1.0])
    return tuple((result[:2] / result[2]).tolist())


def complete_frames() -> list[dict[int, np.ndarray]]:
    layout = default_layout()
    machine_to_pixel = np.array(
        [[1.7, 0.15, 240.0], [0.12, 1.35, 130.0], [0.0004, -0.0003, 1.0]]
    )
    frame = {
        marker_id: np.asarray(
            [
                project(machine_to_pixel, point)
                for point in layout.marker_corner_machine_xy(marker_id)
            ]
        )
        for marker_id in range(6)
    }
    return [{marker_id: corners.copy() for marker_id, corners in frame.items()} for _ in range(12)]


def test_record_uses_held_out_markers_and_is_display_only() -> None:
    result = build_aruco_session_record(
        serial="231122070403",
        frame_size=(1280, 720),
        layout=default_layout(),
        complete_frames=complete_frames(),
        captured_at_utc="2026-07-28T12:00:00Z",
    )

    assert result.record["motion_permission"] == "display_only"
    assert result.record["fit_marker_ids"] == [0, 1, 3, 4]
    assert result.record["validation_marker_ids"] == [2, 5]
    assert result.record["validation"]["max_error_mm"] == pytest.approx(0.0, abs=1e-8)


def test_record_rejects_fewer_than_12_complete_frames() -> None:
    with pytest.raises(SessionCalibrationError, match="12 complete frames"):
        build_aruco_session_record(
            serial="231122070403",
            frame_size=(1280, 720),
            layout=default_layout(),
            complete_frames=complete_frames()[:11],
            captured_at_utc="2026-07-28T12:00:00Z",
        )


def test_record_rejects_excessive_held_out_error() -> None:
    frames = complete_frames()
    for frame in frames:
        frame[2] = frame[2] + np.array([8.0, -4.0])

    with pytest.raises(SessionCalibrationError, match="held-out"):
        build_aruco_session_record(
            serial="231122070403",
            frame_size=(1280, 720),
            layout=default_layout(),
            complete_frames=frames,
            captured_at_utc="2026-07-28T12:00:00Z",
        )


def test_record_rejects_lower_resolution_stream() -> None:
    with pytest.raises(SessionCalibrationError, match="1280x720"):
        build_aruco_session_record(
            serial="231122070403",
            frame_size=(640, 480),
            layout=default_layout(),
            complete_frames=complete_frames(),
            captured_at_utc="2026-07-28T12:00:00Z",
        )


def test_median_is_per_marker_and_corner() -> None:
    first = {0: np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]])}
    middle = {0: first[0] + 2.0}
    last = {0: first[0] + 4.0}

    assert median_marker_corners([first, middle, last], {0})[0] == pytest.approx(middle[0])


def test_detect_marker_corners_keeps_only_known_board_ids() -> None:
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, ARUCO_DICTIONARY_NAME))
    marker = cv2.aruco.generateImageMarker(dictionary, 0, 180)
    image = np.full((300, 300, 3), 255, dtype=np.uint8)
    image[60:240, 60:240] = np.repeat(marker[:, :, None], 3, axis=2)

    corners = detect_marker_corners(image, default_layout())

    assert list(corners) == [0]
    assert corners[0].shape == (4, 2)
    assert np.isfinite(corners[0]).all()


def test_detect_marker_corners_enables_subpixel_refinement(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Detector:
        def __init__(self, dictionary, parameters) -> None:
            captured["parameters"] = parameters

        def detectMarkers(self, grayscale):
            return [], None, []

    monkeypatch.setattr(aruco_plane_calibration.cv2.aruco, "ArucoDetector", Detector)

    assert aruco_plane_calibration.detect_marker_corners(
        np.zeros((32, 32, 3), dtype=np.uint8), default_layout()
    ) == {}
    assert captured["parameters"].cornerRefinementMethod == cv2.aruco.CORNER_REFINE_SUBPIX
