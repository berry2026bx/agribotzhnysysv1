import numpy as np

from vision.realsense.aruco_pose import BoardPose
from vision.realsense.live_yolo_dashboard import (
    annotate_yolo_frame,
    build_parser,
    snapshot_yolo_state,
)
from vision.realsense.object_localization import CameraPoint, MachinePoint
from vision.yolo.detector import Detection


def pose() -> BoardPose:
    return BoardPose(
        rotation=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        translation=(0.0, 0.0, 900.0),
        reprojection_error_px=0.2,
        visible_ids=(0, 1, 2, 3, 4, 5),
        serial="231122070403",
        stream_size=(1280, 720),
        captured_at_utc="2026-08-04T00:00:00Z",
        board_revision="a4-aruco-v3",
    )


def test_snapshot_contains_class_confidence_pixel_xyz_and_machine_xy() -> None:
    detection = Detection(39, "bottle", 0.91, (100.0, 200.0, 140.0, 260.0))
    state = snapshot_yolo_state(
        serial="231122070403",
        detection=detection,
        camera_point=CameraPoint(10.0, 20.0, 500.0),
        machine_point=MachinePoint(30.0, 40.0, 12.0),
        board_pose=pose(),
        error=None,
    )

    assert state["state"] == "ready"
    assert state["motion_permission"] == "display_only"
    assert state["target"]["class_name"] == "bottle"
    assert state["target"]["confidence"] == 0.91
    assert state["target"]["pixel_center_uv"] == {"u": 120.0, "v": 230.0}
    assert state["target"]["camera_xyz_mm"] == {"x": 10.0, "y": 20.0, "z": 500.0}
    assert state["target"]["machine_xy_mm"] == {"x": 30.0, "y": 40.0}


def test_snapshot_omits_coordinates_when_depth_is_invalid() -> None:
    detection = Detection(39, "bottle", 0.91, (100.0, 200.0, 140.0, 260.0))
    state = snapshot_yolo_state(
        serial="231122070403",
        detection=detection,
        camera_point=None,
        machine_point=None,
        board_pose=pose(),
        error="depth must be finite and greater than zero",
    )

    assert state["state"] == "depth_invalid"
    assert state["motion_permission"] == "display_only"
    assert "camera_xyz_mm" not in state["target"]
    assert "machine_xy_mm" not in state["target"]


def test_annotation_returns_same_shape_and_draws_target() -> None:
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    detection = Detection(39, "bottle", 0.91, (100.0, 200.0, 140.0, 260.0))
    annotated = annotate_yolo_frame(image, detection, {"x": 30.0, "y": 40.0})
    assert annotated.shape == image.shape
    assert int(annotated.sum()) > 0


def test_dashboard_parser_requires_a_registration_record_path() -> None:
    args = build_parser().parse_args(
        ["--serial", "231122070403", "--model", "model.pt", "--class-name", "bottle"]
    )
    assert str(args.reference_registration).endswith(
        "docs\\dayuwriter\\calibration\\camera-a-a4-aruco-registration.json"
    )


def test_no_target_state_can_still_report_ready_reference_pose() -> None:
    state = snapshot_yolo_state(
        serial="231122070403",
        detection=None,
        camera_point=None,
        machine_point=None,
        board_pose=pose(),
        error=None,
    )
    assert state["state"] == "no_target"
    assert state["reference_state"] == "ready"
    assert state["mapping_state"] == "unavailable"
    assert state["pose_validation"]["visible_ids"] == [0, 1, 2, 3, 4, 5]
