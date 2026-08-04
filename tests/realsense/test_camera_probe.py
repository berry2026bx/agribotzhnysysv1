import math
from pathlib import Path

import pytest

from vision.realsense import camera_probe
from vision.realsense.camera_probe import (
    CameraProbeError,
    CameraSnapshot,
    build_baseline_record,
    build_parser,
    capture_snapshot,
    center_pixel,
    write_baseline_record,
)


class FakeIntrinsics:
    fx = 600.0
    fy = 601.0
    ppx = 320.0
    ppy = 240.0
    model = "brown_conrady"
    coeffs = (0.0, 0.0, 0.0, 0.0, 0.0)


class FakeVideoProfile:
    def as_video_stream_profile(self):
        return self

    def get_intrinsics(self):
        return FakeIntrinsics()

    def width(self):
        return 640

    def height(self):
        return 480


class FakeColorFrame:
    profile = FakeVideoProfile()

    def get_data(self):
        return [[[1, 2, 3]]]


class FakeDepthFrame:
    def get_distance(self, u, v):
        assert (u, v) == (320, 240)
        return 0.75

    def get_data(self):
        return [[750]]


class FakeFrames:
    def get_color_frame(self):
        return FakeColorFrame()

    def get_depth_frame(self):
        return FakeDepthFrame()


class FakeSensor:
    def get_depth_scale(self):
        return 0.001


class FakeDevice:
    def get_info(self, key):
        assert key == "name"
        return "Intel RealSense D435I"

    def first_depth_sensor(self):
        return FakeSensor()


class FakeProfile:
    def get_device(self):
        return FakeDevice()


class FakeConfig:
    def __init__(self):
        self.serial = None
        self.streams = []

    def enable_device(self, serial):
        self.serial = serial

    def enable_stream(self, *args):
        self.streams.append(args)


class FakePipeline:
    def __init__(self):
        self.config = None
        self.stopped = False

    def start(self, config):
        self.config = config
        return FakeProfile()

    def wait_for_frames(self):
        return object()

    def stop(self):
        self.stopped = True


class FakeAlign:
    def __init__(self, target):
        self.target = target

    def process(self, frames):
        return FakeFrames()


class FakeRealSense:
    class stream:
        color = "color"
        depth = "depth"

    class format:
        rgb8 = "rgb8"
        z16 = "z16"

    class camera_info:
        name = "name"

    def __init__(self):
        self.created_pipeline = FakePipeline()
        self.created_config = FakeConfig()
        self.created_align = None

    def pipeline(self):
        return self.created_pipeline

    def config(self):
        return self.created_config

    def align(self, target):
        self.created_align = FakeAlign(target)
        return self.created_align

    def rs2_deproject_pixel_to_point(self, intrinsics, pixel, depth_m):
        assert intrinsics.fx == 600.0
        assert pixel == [320, 240]
        assert depth_m == 0.75
        return [0.0, 0.0, 0.75]


def test_parser_requires_an_explicit_serial_number() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["--output", "capture.json"])

    args = parser.parse_args(["--serial", "231122070403", "--output", "capture.json"])
    assert args.serial == "231122070403"


def test_center_pixel_uses_the_color_frame_dimensions() -> None:
    assert center_pixel(640, 480) == (320, 240)


class SparseDepthFrame:
    def get_distance(self, u: int, v: int) -> float:
        if (u, v) == (319, 240):
            return 0.75
        return 0.0


def test_find_valid_depth_pixel_falls_back_to_nearby_valid_sample() -> None:
    assert camera_probe.find_valid_depth_pixel(
        SparseDepthFrame(), center=(320, 240), width=640, height=480, radius=1
    ) == (319, 240, 0.75)


def test_capture_snapshot_locks_to_requested_camera_and_aligns_depth_to_color() -> None:
    rs = FakeRealSense()

    snapshot, color, depth = capture_snapshot(rs, "231122070403", warmup_frames=0)

    assert rs.created_config.serial == "231122070403"
    assert rs.created_config.streams == [
        ("depth", 640, 480, "z16", 30),
        ("color", 640, 480, "rgb8", 30),
    ]
    assert rs.created_align.target == "color"
    assert rs.created_pipeline.stopped is True
    assert snapshot.depth_m == 0.75
    assert snapshot.point_camera_m == (0.0, 0.0, 0.75)
    assert color.tolist() == [[[1, 2, 3]]]
    assert depth.tolist() == [[750]]


def test_baseline_record_labels_metric_camera_coordinates() -> None:
    snapshot = CameraSnapshot(
        device_name="Intel RealSense D435I",
        serial="231122070403",
        depth_scale_m_per_unit=0.001,
        color_width=640,
        color_height=480,
        color_fps=30,
        color_format="rgb8",
        depth_width=640,
        depth_height=480,
        depth_fps=30,
        depth_format="z16",
        intrinsics={"fx": 600.0, "fy": 600.0, "ppx": 320.0, "ppy": 240.0},
        pixel_uv=(320, 240),
        depth_m=0.75,
        point_camera_m=(0.0, 0.0, 0.75),
        depth_sample_radius=50,
    )

    record = build_baseline_record(snapshot, captured_at_utc="2026-07-27T00:00:00Z")

    assert record["device"]["serial"] == "231122070403"
    assert record["alignment"] == {"source": "depth", "target": "color"}
    assert record["center_sample"]["depth_m"] == 0.75
    assert record["center_sample"]["point_camera_m"] == {"x": 0.0, "y": 0.0, "z": 0.75}
    assert record["depth_sampling"]["radius_px"] == 50
    assert record["camera_coordinate_convention"] == {
        "x": "right",
        "y": "down",
        "z": "forward",
        "unit": "m",
    }


@pytest.mark.parametrize("depth_m", [0.0, -0.01, math.nan, math.inf])
def test_baseline_record_rejects_nonphysical_depth(depth_m: float) -> None:
    snapshot = CameraSnapshot(
        device_name="Intel RealSense D435I",
        serial="231122070403",
        depth_scale_m_per_unit=0.001,
        color_width=640,
        color_height=480,
        color_fps=30,
        color_format="rgb8",
        depth_width=640,
        depth_height=480,
        depth_fps=30,
        depth_format="z16",
        intrinsics={"fx": 600.0, "fy": 600.0, "ppx": 320.0, "ppy": 240.0},
        pixel_uv=(320, 240),
        depth_m=depth_m,
        point_camera_m=(0.0, 0.0, depth_m),
    )

    with pytest.raises(CameraProbeError, match="depth"):
        build_baseline_record(snapshot, captured_at_utc="2026-07-27T00:00:00Z")


def test_write_baseline_record_creates_parent_directory(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "capture.json"
    record = {"schema_version": 1}

    write_baseline_record(output, record)

    assert output.read_text(encoding="utf-8") == '{\n  "schema_version": 1\n}\n'
