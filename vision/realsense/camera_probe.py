"""Capture a serial-locked, read-only RealSense baseline without GRBL access."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


COLOR_WIDTH = 640
COLOR_HEIGHT = 480
FRAME_RATE = 30
DEFAULT_DEPTH_SAMPLE_RADIUS = 5


class CameraProbeError(RuntimeError):
    """Raised when a camera baseline cannot be measured reliably."""


@dataclass(frozen=True)
class CameraSnapshot:
    device_name: str
    serial: str
    depth_scale_m_per_unit: float
    color_width: int
    color_height: int
    color_fps: int
    color_format: str
    depth_width: int
    depth_height: int
    depth_fps: int
    depth_format: str
    intrinsics: dict[str, Any]
    pixel_uv: tuple[int, int]
    depth_m: float
    point_camera_m: tuple[float, float, float]
    depth_sample_radius: int = DEFAULT_DEPTH_SAMPLE_RADIUS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture one read-only RealSense RGB/depth/3D baseline."
    )
    parser.add_argument("--serial", required=True, help="Exact RealSense serial number")
    parser.add_argument("--output", required=True, type=Path, help="Output JSON path")
    parser.add_argument(
        "--save-frames",
        type=Path,
        help="Optional directory for color.npy and depth.npy",
    )
    parser.add_argument(
        "--warmup-frames",
        type=int,
        default=30,
        help="Frames discarded before capture (default: 30)",
    )
    parser.add_argument(
        "--depth-sample-radius",
        type=int,
        default=DEFAULT_DEPTH_SAMPLE_RADIUS,
        help=(
            "Search radius around the color center for a valid depth sample "
            f"(default: {DEFAULT_DEPTH_SAMPLE_RADIUS})"
        ),
    )
    return parser


def center_pixel(width: int, height: int) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        raise CameraProbeError(f"invalid color dimensions: {width}x{height}")
    return width // 2, height // 2


def find_valid_depth_pixel(
    depth_frame: Any,
    *,
    center: tuple[int, int],
    width: int,
    height: int,
    radius: int,
) -> tuple[int, int, float]:
    """Return the nearest finite positive depth sample around ``center``."""
    if radius < 0:
        raise CameraProbeError("depth sample radius must be non-negative")
    center_u, center_v = center
    if not (0 <= center_u < width and 0 <= center_v < height):
        raise CameraProbeError(f"center pixel is outside {width}x{height}: {center!r}")

    for distance in range(radius + 1):
        offsets = [
            (du, dv)
            for dv in range(-distance, distance + 1)
            for du in range(-distance, distance + 1)
            if max(abs(du), abs(dv)) == distance
        ]
        offsets.sort(key=lambda offset: (abs(offset[0]) + abs(offset[1]), offset[1], offset[0]))
        for du, dv in offsets:
            u = center_u + du
            v = center_v + dv
            if not (0 <= u < width and 0 <= v < height):
                continue
            depth_m = float(depth_frame.get_distance(u, v))
            if math.isfinite(depth_m) and depth_m > 0:
                return u, v, depth_m

    raise CameraProbeError(
        f"no valid depth within radius {radius} of pixel {center}: "
        "all sampled depths were non-finite or zero"
    )


def capture_snapshot(
    rs: Any,
    serial: str,
    *,
    warmup_frames: int,
    depth_sample_radius: int = DEFAULT_DEPTH_SAMPLE_RADIUS,
) -> tuple[CameraSnapshot, np.ndarray, np.ndarray]:
    normalized_serial = _validate_serial(serial)
    if warmup_frames < 0:
        raise CameraProbeError("warmup_frames must be non-negative")
    if depth_sample_radius < 0:
        raise CameraProbeError("depth_sample_radius must be non-negative")

    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_device(normalized_serial)
    config.enable_stream(
        rs.stream.depth,
        COLOR_WIDTH,
        COLOR_HEIGHT,
        rs.format.z16,
        FRAME_RATE,
    )
    config.enable_stream(
        rs.stream.color,
        COLOR_WIDTH,
        COLOR_HEIGHT,
        rs.format.rgb8,
        FRAME_RATE,
    )

    profile = pipeline.start(config)
    try:
        device = profile.get_device()
        depth_scale = float(device.first_depth_sensor().get_depth_scale())
        _require_positive_finite(depth_scale, "depth scale")

        align_to_color = rs.align(rs.stream.color)
        for _ in range(warmup_frames):
            pipeline.wait_for_frames()
        aligned_frames = align_to_color.process(pipeline.wait_for_frames())
        color_frame = aligned_frames.get_color_frame()
        depth_frame = aligned_frames.get_depth_frame()
        if not color_frame or not depth_frame:
            raise CameraProbeError("aligned color or depth frame is unavailable")

        color_profile = color_frame.profile.as_video_stream_profile()
        intrinsics = color_profile.get_intrinsics()
        color_width = int(color_profile.width())
        color_height = int(color_profile.height())
        requested_pixel_uv = center_pixel(color_width, color_height)
        sample_u, sample_v, depth_m = find_valid_depth_pixel(
            depth_frame,
            center=requested_pixel_uv,
            width=color_width,
            height=color_height,
            radius=depth_sample_radius,
        )
        pixel_uv = (sample_u, sample_v)
        point = rs.rs2_deproject_pixel_to_point(
            intrinsics, [pixel_uv[0], pixel_uv[1]], depth_m
        )
        point_camera_m = tuple(float(value) for value in point)
        if len(point_camera_m) != 3 or not all(math.isfinite(value) for value in point_camera_m):
            raise CameraProbeError(f"invalid deprojected point: {point_camera_m!r}")

        snapshot = CameraSnapshot(
            device_name=device.get_info(rs.camera_info.name),
            serial=normalized_serial,
            depth_scale_m_per_unit=depth_scale,
            color_width=color_width,
            color_height=color_height,
            color_fps=FRAME_RATE,
            color_format="rgb8",
            depth_width=color_width,
            depth_height=color_height,
            depth_fps=FRAME_RATE,
            depth_format="z16",
            intrinsics={
                "fx": float(intrinsics.fx),
                "fy": float(intrinsics.fy),
                "ppx": float(intrinsics.ppx),
                "ppy": float(intrinsics.ppy),
                "model": str(intrinsics.model),
                "coeffs": [float(value) for value in intrinsics.coeffs],
            },
            pixel_uv=pixel_uv,
            depth_m=depth_m,
            point_camera_m=point_camera_m,
            depth_sample_radius=depth_sample_radius,
        )
        return snapshot, np.asanyarray(color_frame.get_data()).copy(), np.asanyarray(
            depth_frame.get_data()
        ).copy()
    finally:
        pipeline.stop()


def build_baseline_record(
    snapshot: CameraSnapshot, *, captured_at_utc: str
) -> dict[str, Any]:
    _validate_snapshot(snapshot)
    return {
        "schema_version": 1,
        "captured_at_utc": captured_at_utc,
        "device": {"name": snapshot.device_name, "serial": snapshot.serial},
        "streams": {
            "color": {
                "width_px": snapshot.color_width,
                "height_px": snapshot.color_height,
                "fps": snapshot.color_fps,
                "format": snapshot.color_format,
            },
            "depth": {
                "width_px": snapshot.depth_width,
                "height_px": snapshot.depth_height,
                "fps": snapshot.depth_fps,
                "format": snapshot.depth_format,
                "scale_m_per_unit": snapshot.depth_scale_m_per_unit,
            },
        },
        "alignment": {"source": "depth", "target": "color"},
        "color_intrinsics": snapshot.intrinsics,
        "center_sample": {
            "pixel_uv": {"u": snapshot.pixel_uv[0], "v": snapshot.pixel_uv[1]},
            "depth_m": snapshot.depth_m,
            "point_camera_m": {
                "x": snapshot.point_camera_m[0],
                "y": snapshot.point_camera_m[1],
                "z": snapshot.point_camera_m[2],
            },
        },
        "depth_sampling": {
            "requested_pixel_uv": {
                "u": snapshot.color_width // 2,
                "v": snapshot.color_height // 2,
            },
            "strategy": "center_outward_first_valid",
            "radius_px": snapshot.depth_sample_radius,
        },
        "camera_coordinate_convention": {
            "x": "right",
            "y": "down",
            "z": "forward",
            "unit": "m",
        },
    }


def write_baseline_record(output: Path, record: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def _validate_serial(serial: str) -> str:
    if not isinstance(serial, str) or not serial.strip():
        raise CameraProbeError("an explicit non-empty camera serial is required")
    return serial.strip()


def _validate_snapshot(snapshot: CameraSnapshot) -> None:
    _validate_serial(snapshot.serial)
    _require_positive_finite(snapshot.depth_scale_m_per_unit, "depth scale")
    _require_positive_finite(snapshot.depth_m, "depth")
    if len(snapshot.point_camera_m) != 3 or not all(
        math.isfinite(value) for value in snapshot.point_camera_m
    ):
        raise CameraProbeError(f"invalid deprojected point: {snapshot.point_camera_m!r}")


def _require_positive_finite(value: float, label: str) -> None:
    if not math.isfinite(value) or value <= 0:
        raise CameraProbeError(f"{label} must be finite and greater than zero: {value!r}")


def main() -> int:
    args = build_parser().parse_args()
    try:
        import pyrealsense2 as rs

        snapshot, color, depth = capture_snapshot(
            rs,
            args.serial,
            warmup_frames=args.warmup_frames,
            depth_sample_radius=args.depth_sample_radius,
        )
        captured_at_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        record = build_baseline_record(snapshot, captured_at_utc=captured_at_utc)
        write_baseline_record(args.output, record)
        if args.save_frames is not None:
            args.save_frames.mkdir(parents=True, exist_ok=True)
            np.save(args.save_frames / "color.npy", color)
            np.save(args.save_frames / "depth.npy", depth)
        print(f"Read-only baseline written to {args.output}")
        return 0
    except (CameraProbeError, OSError, RuntimeError) as exc:
        print(f"Camera baseline failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
