import numpy as np
import pytest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer
from threading import Thread

from vision.realsense.aruco_reference_board import default_layout
from vision.realsense.live_red_target_dashboard import (
    ArucoReferenceTracker,
    BoardRegistrationService,
    DashboardError,
    SnapshotStore,
    _html_page,
    _make_handler,
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


def test_tracker_keeps_a_validated_mapping_for_small_marker_jitter() -> None:
    tracker = ArucoReferenceTracker(layout=default_layout(), registration=registration())
    markers = all_markers()

    for _ in range(11):
        tracker.update(markers)
    ready = tracker.update(markers)
    jittered = {marker_id: corners + np.array([0.2, -0.1]) for marker_id, corners in markers.items()}

    stable = tracker.update(jittered)

    assert ready.state == "ready"
    assert stable.state == "ready"
    assert stable.validation == ready.validation
    assert stable.matrix_pixel_to_machine == pytest.approx(ready.matrix_pixel_to_machine)

    moved = {marker_id: corners + np.array([10.0, 0.0]) for marker_id, corners in markers.items()}
    invalidated = tracker.update(moved)

    assert invalidated.state == "reference_moved"
    assert invalidated.matrix_pixel_to_machine is None


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


def test_registration_service_writes_display_only_record_and_unblocks_tracker(tmp_path) -> None:
    tracker = ArucoReferenceTracker(layout=default_layout(), registration=None)
    path = tmp_path / "registration.json"
    service = BoardRegistrationService(
        layout=default_layout(),
        registration_path=path,
        tracker=tracker,
        now=lambda: "2026-07-28T12:00:00Z",
    )

    record = service.register({"operator_confirmed": True})

    assert record["motion_permission"] == "display_only"
    assert path.exists()
    assert tracker.update(all_markers()).state == "collecting_reference_frames"


def test_registration_service_rejects_any_payload_other_than_confirmation(tmp_path) -> None:
    service = BoardRegistrationService(
        layout=default_layout(),
        registration_path=tmp_path / "registration.json",
        tracker=ArucoReferenceTracker(layout=default_layout(), registration=None),
        now=lambda: "2026-07-28T12:00:00Z",
    )

    with pytest.raises(DashboardError, match="operator_confirmed"):
        service.register({"x": 10})


def test_registration_endpoint_accepts_confirmation_and_rejects_axis_payload(tmp_path) -> None:
    tracker = ArucoReferenceTracker(layout=default_layout(), registration=None)
    service = BoardRegistrationService(
        layout=default_layout(),
        registration_path=tmp_path / "registration.json",
        tracker=tracker,
        now=lambda: "2026-07-28T12:00:00Z",
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(SnapshotStore(), service))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}/register-board"
    try:
        response = urlopen(
            Request(
                base_url,
                data=b'{"operator_confirmed":true}',
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        )
        assert response.status == 200
        with pytest.raises(HTTPError) as error:
            urlopen(
                Request(
                    base_url,
                    data=b'{"x":10}',
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
            )
        assert error.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)


def test_wizard_has_registration_instruction_and_no_motion_controls() -> None:
    page = _html_page()

    assert "Reference board registration" in page
    assert "I aligned P0, X+30 mm, and Y+30 mm" in page
    assert "Register board" in page
    assert "No GRBL motion is available in this page." in page
    assert "G0" not in page
    assert "$J" not in page


def test_dashboard_page_uses_high_resolution_coordinate_overlay() -> None:
    page = _html_page()

    assert 'viewBox="0 0 1280 720"' in page
    assert "const DISPLAY_WIDTH=1280" in page
    assert "const scale=stage.clientWidth/DISPLAY_WIDTH" in page


def test_dashboard_page_has_prominent_live_machine_xy_readout() -> None:
    page = _html_page()

    assert 'id="target-coordinate"' in page
    assert 'id="target-x"' in page
    assert 'id="target-y"' in page
    assert 'id="target-coordinate-state"' in page
    assert "function renderTargetCoordinate(state)" in page
    assert "state.machine_xy_mm" in page


def test_dashboard_page_places_live_coordinates_before_debug_state() -> None:
    page = _html_page()

    assert page.index('id="target-coordinate"') < page.index('id="state"')
