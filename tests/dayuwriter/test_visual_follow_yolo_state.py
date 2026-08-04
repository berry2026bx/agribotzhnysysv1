import pytest

from communication.dayuwriter.visual_follow import LiveTarget, VisualFollowError, parse_live_target


def yolo_payload(*, x=12.0, y=8.0, class_name="bottle"):
    return {
        "state": "ready",
        "mapping_state": "available",
        "motion_permission": "display_only",
        "reference_state": "ready",
        "pose_validation": {"visible_ids": [0, 1, 2, 3, 4, 5]},
        "target": {
            "class_name": class_name,
            "confidence": 0.91,
            "camera_xyz_mm": {"x": 10.0, "y": 20.0, "z": 500.0},
            "machine_xyz_mm": {"x": x, "y": y, "z": 5.0},
            "machine_xy_mm": {"x": x, "y": y},
        },
        "machine_xy_mm": {"x": x, "y": y},
    }


def test_parse_yolo_target_preserves_requested_class_and_xyz() -> None:
    target = parse_live_target(yolo_payload(), requested_class="bottle")
    assert target == LiveTarget(12.0, 8.0, requested_class="bottle", camera_xyz_mm=(10.0, 20.0, 500.0), machine_xyz_mm=(12.0, 8.0, 5.0))


def test_parse_yolo_target_rejects_class_mismatch() -> None:
    with pytest.raises(VisualFollowError, match="class"):
        parse_live_target(yolo_payload(class_name="cup"), requested_class="bottle")


def test_parse_yolo_target_rejects_missing_reference_pose() -> None:
    payload = yolo_payload()
    payload["reference_state"] = "reference_lost"
    with pytest.raises(VisualFollowError, match="reference"):
        parse_live_target(payload, requested_class="bottle")


def test_parse_yolo_target_rejects_missing_depth_xyz() -> None:
    payload = yolo_payload()
    payload["target"].pop("camera_xyz_mm")
    with pytest.raises(VisualFollowError, match="camera_xyz"):
        parse_live_target(payload, requested_class="bottle")


def test_continuous_fetcher_receives_requested_class() -> None:
    from communication.dayuwriter.visual_follow import fetch_ready_live_target

    seen = []
    target = fetch_ready_live_target(
        "loopback",
        fetcher=lambda _url: yolo_payload(),
        requested_class="bottle",
    )
    assert target.requested_class == "bottle"
