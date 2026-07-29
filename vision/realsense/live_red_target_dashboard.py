"""Loopback-only D435i red-target coordinate display with no GRBL access."""

from __future__ import annotations

import argparse
import json
import math
import struct
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import numpy as np

from .aruco_plane_calibration import (
    ArucoSessionResult,
    REQUIRED_COMPLETE_FRAMES,
    SessionCalibrationError,
    build_aruco_session_record,
    detect_marker_corners,
)
from .aruco_reference_board import (
    ArucoBoardLayout,
    BoardRegistrationError,
    build_registration_record,
    default_layout,
    load_registration,
)
from .plane_mapping import PlaneMappingError, predict_machine_xy
from .red_target import (
    RedTarget,
    RedTargetConfig,
    RedTargetError,
    TargetObservation,
    find_red_target,
    observe_target,
)


COLOR_WIDTH = 1280
COLOR_HEIGHT = 720
DEPTH_WIDTH = 640
DEPTH_HEIGHT = 480
FRAME_RATE = 30
# D435i A's measured subpixel corner noise reached 5.58 px at p99 in a
# stationary 180-frame sample; larger movement invalidates the session.
MAX_REFERENCE_MARKER_DRIFT_PX = 8.0
REFERENCE_BOARD_TARGET_MARGIN_MM = 5.0


class DashboardError(RuntimeError):
    """Raised for invalid dashboard configuration or camera failures."""


@dataclass(frozen=True)
class Calibration:
    serial: str
    pixel_to_machine: np.ndarray | None


@dataclass(frozen=True)
class ReferenceStatus:
    """Current display-only validity of the fixed A4 reference board."""

    state: str
    detail: str | None
    marker_corners_uv: dict[int, tuple[tuple[float, float], ...]]
    matrix_pixel_to_machine: np.ndarray | None
    validation: dict[str, Any] | None


class ArucoReferenceTracker:
    """Build a safe display mapping only from a registered, visible reference board."""

    def __init__(
        self,
        *,
        layout: ArucoBoardLayout,
        registration: dict[str, object] | None,
        serial: str = "231122070403",
        registration_detail: str | None = None,
    ) -> None:
        self.layout = layout
        self._registration = registration
        self._serial = serial
        self._registration_detail = registration_detail
        self._complete_frames: list[dict[int, np.ndarray]] = []
        self._session: ArucoSessionResult | None = None

    def confirm_registration(self, registration: dict[str, object]) -> None:
        """Accept a locally confirmed display-only board registration and restart collection."""
        if registration.get("operator_confirmed") is not True:
            raise DashboardError("board registration requires operator confirmation")
        if registration.get("motion_permission") != "display_only":
            raise DashboardError("board registration must be display_only")
        self._registration = registration
        self._registration_detail = None
        self._complete_frames.clear()
        self._session = None

    def update(self, corners_uv: Mapping[int, np.ndarray]) -> ReferenceStatus:
        """Return a new mapping status and never retain a stale matrix after failure."""
        marker_corners = _serializable_marker_corners(corners_uv)
        if self._registration is None:
            return ReferenceStatus(
                "registration_required",
                self._registration_detail or "reference board registration is required",
                marker_corners,
                None,
                None,
            )
        try:
            normalized = _complete_reference_frame(corners_uv, self.layout)
        except SessionCalibrationError as exc:
            self._complete_frames.clear()
            self._session = None
            return ReferenceStatus("reference_lost", str(exc), marker_corners, None, None)

        if self._session is not None:
            max_drift_px = _maximum_marker_corner_drift(
                normalized, self._session.median_corners_uv
            )
            if max_drift_px > MAX_REFERENCE_MARKER_DRIFT_PX:
                self._complete_frames.clear()
                self._session = None
                return ReferenceStatus(
                    "reference_moved",
                    f"reference markers moved by {max_drift_px:.2f} px; collecting a new session",
                    marker_corners,
                    None,
                    None,
                )
            return ReferenceStatus(
                "ready",
                None,
                marker_corners,
                self._session.matrix_pixel_to_machine,
                self._session.record["validation"],
            )

        if len(self._complete_frames) < REQUIRED_COMPLETE_FRAMES:
            self._complete_frames.append(normalized)
            if len(self._complete_frames) < REQUIRED_COMPLETE_FRAMES:
                return ReferenceStatus(
                    "collecting_reference_frames",
                    f"{len(self._complete_frames)}/{REQUIRED_COMPLETE_FRAMES} complete frames",
                    marker_corners,
                    None,
                    None,
                )
            complete_frames = self._complete_frames

        try:
            result = build_aruco_session_record(
                serial=self._serial,
                frame_size=(COLOR_WIDTH, COLOR_HEIGHT),
                layout=self.layout,
                complete_frames=complete_frames,
                captured_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            )
        except SessionCalibrationError as exc:
            self._complete_frames.clear()
            return ReferenceStatus("calibration_rejected", str(exc), marker_corners, None, None)
        self._session = result
        return ReferenceStatus(
            "ready",
            None,
            marker_corners,
            result.matrix_pixel_to_machine,
            result.record["validation"],
        )


class BoardRegistrationService:
    """Persist exactly one local operator confirmation; it has no motion fields."""

    def __init__(
        self,
        *,
        layout: ArucoBoardLayout,
        registration_path: Path,
        tracker: ArucoReferenceTracker,
        now: callable | None = None,
    ) -> None:
        self._layout = layout
        self._registration_path = registration_path
        self._tracker = tracker
        self._now = now or (lambda: datetime.now(timezone.utc).replace(microsecond=0).isoformat())

    def register(self, payload: object) -> dict[str, object]:
        if payload != {"operator_confirmed": True}:
            raise DashboardError("register-board requires only operator_confirmed: true")
        record = build_registration_record(self._layout, self._now())
        self._registration_path.parent.mkdir(parents=True, exist_ok=True)
        self._registration_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        self._tracker.confirm_registration(record)
        return record


@dataclass(frozen=True)
class DashboardSnapshot:
    frame_bmp: bytes
    state: dict[str, Any]


class SnapshotStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot = DashboardSnapshot(
            frame_bmp=make_bmp_bytes(np.zeros((1, 1, 3), dtype=np.uint8)),
            state={
                "state": "starting",
                "motion_permission": "display_only",
                "error": None,
            },
        )

    def publish(self, frame_bmp: bytes, state: dict[str, Any]) -> None:
        with self._lock:
            self._snapshot = DashboardSnapshot(frame_bmp=frame_bmp, state=state)

    def read(self) -> DashboardSnapshot:
        with self._lock:
            return self._snapshot


def make_bmp_bytes(rgb: np.ndarray) -> bytes:
    """Encode an RGB uint8 image as a standards-compliant uncompressed BMP."""
    image = np.asarray(rgb)
    if image.ndim != 3 or image.shape[2] != 3:
        raise DashboardError("RGB image must have shape (height, width, 3)")
    height, width = image.shape[:2]
    if height <= 0 or width <= 0:
        raise DashboardError("RGB image dimensions must be positive")
    image = image.astype(np.uint8, copy=False)
    row_bytes = width * 3
    row_padding = (-row_bytes) % 4
    pixel_data_size = (row_bytes + row_padding) * height
    file_size = 14 + 40 + pixel_data_size
    file_header = b"BM" + struct.pack("<IHHI", file_size, 0, 0, 54)
    dib_header = struct.pack(
        "<IiiHHIIiiII",
        40,
        width,
        height,
        1,
        24,
        0,
        pixel_data_size,
        2835,
        2835,
        0,
        0,
    )
    padding = b"\x00" * row_padding
    rows = []
    for row in image[::-1, :, ::-1]:
        rows.append(row.tobytes())
        rows.append(padding)
    return file_header + dib_header + b"".join(rows)


def snapshot_state(
    target: RedTarget | None,
    observation: TargetObservation | None,
    *,
    error: str | None,
    reference: ReferenceStatus | None = None,
    plane_machine_xy_mm: tuple[float, float] | None = None,
) -> dict[str, Any]:
    """Serialize the current display-only camera result for the browser."""
    state: dict[str, Any] = {
        "motion_permission": "display_only",
        "error": error,
    }
    if reference is not None:
        state.update(
            reference_snapshot_state(
                state=reference.state,
                detail=reference.detail,
                marker_corners=reference.marker_corners_uv,
                validation=reference.validation,
            )
        )
    if target is None:
        state["state"] = "no_target" if error is None else "camera_error"
        return state

    state["target"] = {
        "center_uv": {"u": target.center_uv[0], "v": target.center_uv[1]},
        "bbox_uvwh": {
            "u": target.bbox_uvwh[0],
            "v": target.bbox_uvwh[1],
            "width": target.bbox_uvwh[2],
            "height": target.bbox_uvwh[3],
        },
        "area_px": target.area_px,
        "fill_ratio": target.fill_ratio,
    }
    if observation is None:
        if plane_machine_xy_mm is not None:
            x_mm, y_mm = plane_machine_xy_mm
            if not math.isfinite(x_mm) or not math.isfinite(y_mm):
                raise DashboardError("plane_machine_xy_mm must be finite")
            state.update(
                {
                    "state": "ready",
                    "mapping_state": "available",
                    "depth_state": "unavailable",
                    "depth_error": error,
                    "error": None,
                    "machine_xy_mm": {"x": x_mm, "y": y_mm},
                }
            )
            return state
        state["state"] = "depth_unavailable"
        return state

    state.update(
        {
            "state": "ready",
            "mapping_state": "available" if observation.machine_xy_mm is not None else "unavailable",
            "depth_m": observation.depth_m,
            "depth_sample_uv": {
                "u": observation.depth_sample_uv[0],
                "v": observation.depth_sample_uv[1],
            },
            "camera_xyz_m": {
                "x": observation.camera_xyz_m[0],
                "y": observation.camera_xyz_m[1],
                "z": observation.camera_xyz_m[2],
            },
        }
    )
    if observation.machine_xy_mm is not None:
        state["machine_xy_mm"] = {
            "x": observation.machine_xy_mm[0],
            "y": observation.machine_xy_mm[1],
        }
    return state


def reference_snapshot_state(
    *,
    state: str,
    detail: str | None,
    marker_corners: Mapping[int, tuple[tuple[float, float], ...]],
    validation: dict[str, Any] | None,
) -> dict[str, Any]:
    """Serialize reference validity without granting any motion capability."""
    return {
        "motion_permission": "display_only",
        "reference": {
            "state": state,
            "detail": detail,
            "visible_marker_ids": sorted(marker_corners),
            "marker_corners_uv": {
                str(marker_id): [
                    {"u": float(corner[0]), "v": float(corner[1])}
                    for corner in corners
                ]
                for marker_id, corners in sorted(marker_corners.items())
            },
            "validation": validation,
        },
    }


def _reference_board_candidate_filter(
    layout: ArucoBoardLayout,
    pixel_to_machine: np.ndarray,
) -> Callable[[RedTarget], bool]:
    """Accept only target centres within the physical A4 reference plane."""

    paper_corners = (
        layout.machine_xy_for_board((0.0, 0.0)),
        layout.machine_xy_for_board((layout.width_mm, 0.0)),
        layout.machine_xy_for_board((layout.width_mm, layout.height_mm)),
        layout.machine_xy_for_board((0.0, layout.height_mm)),
    )
    x_values, y_values = zip(*paper_corners, strict=True)
    x_min = min(x_values) - REFERENCE_BOARD_TARGET_MARGIN_MM
    x_max = max(x_values) + REFERENCE_BOARD_TARGET_MARGIN_MM
    y_min = min(y_values) - REFERENCE_BOARD_TARGET_MARGIN_MM
    y_max = max(y_values) + REFERENCE_BOARD_TARGET_MARGIN_MM

    def accepts(candidate: RedTarget) -> bool:
        try:
            x_mm, y_mm = predict_machine_xy(pixel_to_machine, candidate.center_uv)
        except PlaneMappingError:
            return False
        return x_min <= x_mm <= x_max and y_min <= y_mm <= y_max

    return accepts


def _complete_reference_frame(
    corners_uv: Mapping[int, np.ndarray], layout: ArucoBoardLayout
) -> dict[int, np.ndarray]:
    expected_ids = {marker.identifier for marker in layout.markers}
    missing = sorted(expected_ids - set(corners_uv))
    if missing:
        raise SessionCalibrationError(f"required reference marker ids are missing: {missing}")
    frame: dict[int, np.ndarray] = {}
    for marker_id in sorted(expected_ids):
        corners = np.asarray(corners_uv[marker_id], dtype=float)
        if corners.shape == (1, 4, 2):
            corners = corners[0]
        if corners.shape != (4, 2) or not np.all(np.isfinite(corners)):
            raise SessionCalibrationError(
                f"reference marker {marker_id} must have finite (4, 2) corners"
            )
        frame[marker_id] = corners.copy()
    return frame


def _maximum_marker_corner_drift(
    observed: Mapping[int, np.ndarray], baseline: Mapping[int, np.ndarray]
) -> float:
    """Return the largest Euclidean RGB-pixel corner displacement."""
    distances = [
        np.linalg.norm(observed[marker_id] - baseline[marker_id], axis=1)
        for marker_id in observed
    ]
    return float(np.max(np.concatenate(distances)))


def _serializable_marker_corners(
    corners_uv: Mapping[int, np.ndarray]
) -> dict[int, tuple[tuple[float, float], ...]]:
    result: dict[int, tuple[tuple[float, float], ...]] = {}
    for marker_id, corners in corners_uv.items():
        array = np.asarray(corners, dtype=float)
        if array.shape == (1, 4, 2):
            array = array[0]
        if array.shape == (4, 2) and np.all(np.isfinite(array)):
            result[int(marker_id)] = tuple((float(point[0]), float(point[1])) for point in array)
    return dict(sorted(result.items()))


def load_calibration(path: Path, serial: str) -> Calibration:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DashboardError(f"cannot read calibration artifact: {path}") from exc
    if not isinstance(record, dict):
        raise DashboardError("calibration artifact must be a JSON object")
    camera = record.get("camera")
    if not isinstance(camera, dict) or camera.get("serial") != serial:
        raise DashboardError("calibration camera serial does not match --serial")
    if record.get("motion_permission") != "display_only":
        raise DashboardError("calibration artifact must be marked display_only")
    matrix = np.asarray(record.get("matrix_pixel_to_machine"), dtype=float)
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
        raise DashboardError("calibration artifact has no finite 3x3 mapping matrix")
    return Calibration(serial=serial, pixel_to_machine=matrix)


def run_camera_worker(
    store: SnapshotStore,
    stop_event: threading.Event,
    *,
    calibration: Calibration,
    target_config: RedTargetConfig,
    warmup_frames: int,
    depth_sample_radius: int,
    reference_tracker: ArucoReferenceTracker | None = None,
) -> None:
    """Read D435i frames until stopped and publish the latest display snapshot."""
    try:
        import pyrealsense2 as rs

        pipeline = rs.pipeline()
        config = rs.config()
        config.enable_device(calibration.serial)
        config.enable_stream(rs.stream.depth, DEPTH_WIDTH, DEPTH_HEIGHT, rs.format.z16, FRAME_RATE)
        config.enable_stream(rs.stream.color, COLOR_WIDTH, COLOR_HEIGHT, rs.format.rgb8, FRAME_RATE)
        profile = pipeline.start(config)
    except Exception as exc:
        store.publish(
            make_bmp_bytes(np.zeros((1, 1, 3), dtype=np.uint8)),
            snapshot_state(None, None, error=f"camera_start_failed: {exc}"),
        )
        return

    try:
        align_to_color = rs.align(rs.stream.color)
        for _ in range(warmup_frames):
            if stop_event.is_set():
                return
            pipeline.wait_for_frames()
        while not stop_event.is_set():
            frames = align_to_color.process(pipeline.wait_for_frames())
            color_frame = frames.get_color_frame()
            depth_frame = frames.get_depth_frame()
            if not color_frame or not depth_frame:
                store.publish(
                    make_bmp_bytes(np.zeros((1, 1, 3), dtype=np.uint8)),
                    snapshot_state(None, None, error="aligned_color_or_depth_unavailable"),
                )
                continue
            rgb = np.asanyarray(color_frame.get_data()).copy()
            reference: ReferenceStatus | None = None
            pixel_to_machine = calibration.pixel_to_machine
            if reference_tracker is not None:
                try:
                    reference = reference_tracker.update(
                        detect_marker_corners(rgb, reference_tracker.layout)
                    )
                    pixel_to_machine = reference.matrix_pixel_to_machine
                except SessionCalibrationError as exc:
                    reference = ReferenceStatus("reference_lost", str(exc), {}, None, None)
                    pixel_to_machine = None
            candidate_filter: Callable[[RedTarget], bool] | None = None
            if (
                reference_tracker is not None
                and reference is not None
                and reference.state == "ready"
                and pixel_to_machine is not None
            ):
                candidate_filter = _reference_board_candidate_filter(
                    reference_tracker.layout, pixel_to_machine
                )
            target = find_red_target(
                rgb, target_config, candidate_filter=candidate_filter
            )
            if target is None:
                store.publish(
                    make_bmp_bytes(rgb), snapshot_state(None, None, error=None, reference=reference)
                )
                continue
            try:
                color_profile = color_frame.profile.as_video_stream_profile()
                observation = observe_target(
                    target,
                    depth_frame=depth_frame,
                    color_intrinsics=color_profile.get_intrinsics(),
                    deproject=rs.rs2_deproject_pixel_to_point,
                    pixel_to_machine=pixel_to_machine,
                    width=int(color_profile.width()),
                    height=int(color_profile.height()),
                    depth_sample_radius=depth_sample_radius,
                )
            except RedTargetError as exc:
                plane_machine_xy_mm: tuple[float, float] | None = None
                if pixel_to_machine is not None:
                    try:
                        plane_machine_xy_mm = predict_machine_xy(
                            pixel_to_machine, target.center_uv
                        )
                    except PlaneMappingError:
                        plane_machine_xy_mm = None
                store.publish(
                    make_bmp_bytes(rgb),
                    snapshot_state(
                        target,
                        None,
                        error=str(exc),
                        reference=reference,
                        plane_machine_xy_mm=plane_machine_xy_mm,
                    ),
                )
                continue
            store.publish(
                make_bmp_bytes(rgb), snapshot_state(target, observation, error=None, reference=reference)
            )
    except Exception as exc:
        store.publish(
            make_bmp_bytes(np.zeros((1, 1, 3), dtype=np.uint8)),
            snapshot_state(None, None, error=f"camera_runtime_failed: {exc}"),
        )
    finally:
        pipeline.stop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Display-only D435i red target RGB/depth/camera-XYZ/P0-XY dashboard."
    )
    parser.add_argument("--serial", required=True, help="Exact D435i serial number")
    parser.add_argument(
        "--calibration",
        type=Path,
        default=Path("docs/dayuwriter/calibration/camera-a-current-pose-result.json"),
        help="Display-only pixel-to-machine calibration artifact",
    )
    parser.add_argument(
        "--camera-xyz-only",
        action="store_true",
        help="Show pixel/depth/camera XYZ without any machine-plane prediction",
    )
    parser.add_argument(
        "--aruco-reference-board",
        action="store_true",
        help="Derive display-only XY from the registered A4 ArUco reference board",
    )
    parser.add_argument(
        "--reference-registration",
        type=Path,
        default=Path("docs/dayuwriter/calibration/camera-a-a4-aruco-registration.json"),
        help="Display-only A4 reference-board registration record",
    )
    parser.add_argument("--port", type=int, default=8765, help="Loopback HTTP port")
    parser.add_argument(
        "--min-area-px",
        type=int,
        default=RedTargetConfig().min_area_px,
        help="Minimum red target area",
    )
    parser.add_argument("--warmup-frames", type=int, default=120, help="Frames discarded at startup")
    parser.add_argument("--depth-sample-radius", type=int, default=5, help="Depth search radius")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if not 1 <= args.port <= 65535:
            raise DashboardError("--port must be between 1 and 65535")
        if args.warmup_frames < 0 or args.depth_sample_radius < 0:
            raise DashboardError("warmup and depth radius must be non-negative")
        if args.camera_xyz_only and args.aruco_reference_board:
            raise DashboardError("--camera-xyz-only and --aruco-reference-board cannot be combined")
        reference_tracker: ArucoReferenceTracker | None = None
        registration_service: BoardRegistrationService | None = None
        if args.aruco_reference_board:
            layout = default_layout()
            registration: dict[str, object] | None
            registration_detail: str | None = None
            try:
                registration = load_registration(args.reference_registration, layout)
            except BoardRegistrationError as exc:
                registration = None
                registration_detail = str(exc)
            calibration = Calibration(serial=args.serial, pixel_to_machine=None)
            reference_tracker = ArucoReferenceTracker(
                layout=layout,
                registration=registration,
                serial=args.serial,
                registration_detail=registration_detail,
            )
            registration_service = BoardRegistrationService(
                layout=layout,
                registration_path=args.reference_registration,
                tracker=reference_tracker,
            )
        elif args.camera_xyz_only:
            calibration = Calibration(serial=args.serial, pixel_to_machine=None)
        else:
            calibration = load_calibration(args.calibration, args.serial)
        target_config = RedTargetConfig(min_area_px=args.min_area_px)
        store = SnapshotStore()
        stop_event = threading.Event()
        worker = threading.Thread(
            target=run_camera_worker,
            kwargs={
                "store": store,
                "stop_event": stop_event,
                "calibration": calibration,
                "target_config": target_config,
                "warmup_frames": args.warmup_frames,
                "depth_sample_radius": args.depth_sample_radius,
                "reference_tracker": reference_tracker,
            },
            name="d435i-red-target",
            daemon=True,
        )
        server = ThreadingHTTPServer(
            ("127.0.0.1", args.port), _make_handler(store, registration_service)
        )
    except (DashboardError, OSError, RedTargetError) as exc:
        print(f"Live red target dashboard failed: {exc}")
        return 1

    worker.start()
    print(f"Display-only dashboard: http://127.0.0.1:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping display-only dashboard")
    finally:
        stop_event.set()
        server.shutdown()
        server.server_close()
        worker.join(timeout=5.0)
    return 0


def _make_handler(
    store: SnapshotStore, registration_service: BoardRegistrationService | None = None
) -> type[BaseHTTPRequestHandler]:
    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            snapshot = store.read()
            if path == "/":
                self._send_bytes(_html_page().encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/frame.bmp":
                self._send_bytes(snapshot.frame_bmp, "image/bmp")
            elif path == "/state.json":
                self._send_bytes(
                    json.dumps(snapshot.state).encode("utf-8"), "application/json; charset=utf-8"
                )
            else:
                self.send_error(404, "Not Found")

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path != "/register-board" or registration_service is None:
                self.send_error(404, "Not Found")
                return
            try:
                payload = self._read_json_body()
                record = registration_service.register(payload)
            except DashboardError as exc:
                self._send_error_json(400, str(exc))
                return
            self._send_bytes(json.dumps(record).encode("utf-8"), "application/json; charset=utf-8")

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_bytes(self, payload: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _read_json_body(self) -> object:
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise DashboardError("invalid request content length") from exc
            if content_length <= 0 or content_length > 4096:
                raise DashboardError("register-board request body must be between 1 and 4096 bytes")
            try:
                return json.loads(self.rfile.read(content_length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise DashboardError("register-board request must be JSON") from exc

        def _send_error_json(self, status: int, message: str) -> None:
            payload = json.dumps(
                {"motion_permission": "display_only", "error": message}
            ).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

    return DashboardHandler


def _html_page() -> str:
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>D435i Red Target</title>
<style>
body{margin:0;background:#f4f5f3;color:#17201a;font-family:Arial,sans-serif}
  main{display:grid;grid-template-columns:minmax(0,960px) minmax(280px,440px);gap:20px;padding:20px}
  #stage{position:relative;width:100%;max-width:960px;aspect-ratio:16/9;background:#171d18}
  #frame{display:block;width:100%;height:100%}
  #box{position:absolute;border:3px solid #d61f26;display:none;box-sizing:border-box}
  #reference-overlay{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
#reference-overlay polygon{fill:none;stroke-width:2}
aside{display:grid;align-content:start;gap:12px;max-width:440px}
section{background:#fff;border:1px solid #ccd3ca;padding:16px}
h1{font-size:20px;margin:0 0 16px}h2{font-size:16px;margin:0 0 10px}pre{white-space:pre-wrap;word-break:break-word;margin:0;font-size:14px}
  .warn{color:#9d1c21;font-weight:700}
  .coordinate-readout{border-left:4px solid #16803c}.coordinate-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.coordinate-label{display:block;color:#526056;font-size:13px}.coordinate-value{display:block;font-size:28px;line-height:1.15;font-variant-numeric:tabular-nums}.coordinate-unit{color:#526056;font-size:13px}.coordinate-state{margin:12px 0 0;color:#526056;font-size:13px}.coordinate-readout[data-state="unavailable"]{border-left-color:#9d1c21}
  .registration{display:grid;gap:10px}.registration label{line-height:1.35}.registration button{justify-self:start}
  @media(max-width:1400px){main{grid-template-columns:minmax(0,1fr)}aside{max-width:960px}}
  </style></head><body><main><div id="stage"><img id="frame" alt="Live D435i RGB"><div id="box"></div><svg id="reference-overlay" viewBox="0 0 1280 720" aria-hidden="true"></svg></div>
<aside><section id="target-coordinate" class="coordinate-readout" data-state="unavailable" aria-live="polite"><h2>目标相对 P0</h2><div class="coordinate-grid"><div><span class="coordinate-label">X</span><strong id="target-x" class="coordinate-value">--</strong><span class="coordinate-unit">mm</span></div><div><span class="coordinate-label">Y</span><strong id="target-y" class="coordinate-value">--</strong><span class="coordinate-unit">mm</span></div></div><p id="target-coordinate-state" class="coordinate-state">实时红方块坐标</p></section>
<section><h1>Display-only red target</h1><p class="warn">No GRBL motion is available in this page.</p><pre id="state">starting</pre></section>
<section id="reference-registration" class="registration"><h2>Reference board registration</h2><label><input id="registration-confirmation" type="checkbox"> I aligned P0, X+30 mm, and Y+30 mm, and secured the board.</label><button id="register-board" type="button" disabled>Register board</button></section>
<section id="reference-status"><h2>Reference board</h2><pre id="reference-state">waiting for reference data</pre></section></aside></main>
<script>
const DISPLAY_WIDTH=1280, frame=document.getElementById('frame'), stage=document.getElementById('stage'), box=document.getElementById('box'), output=document.getElementById('state'), referenceOutput=document.getElementById('reference-state'), overlay=document.getElementById('reference-overlay'), confirmation=document.getElementById('registration-confirmation'), registerButton=document.getElementById('register-board'), coordinateCard=document.getElementById('target-coordinate'), coordinateX=document.getElementById('target-x'), coordinateY=document.getElementById('target-y'), coordinateState=document.getElementById('target-coordinate-state');
confirmation.addEventListener('change',()=>{registerButton.disabled=!confirmation.checked;});
registerButton.addEventListener('click',async()=>{
  try{const response=await fetch('/register-board',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({operator_confirmed:true})});const body=await response.json();if(!response.ok)throw new Error(body.error||'registration failed');confirmation.checked=false;registerButton.disabled=true;referenceOutput.textContent=JSON.stringify(body,null,2);}catch(error){referenceOutput.textContent='registration failed: '+error;}
});
function markerColor(reference){if(!reference)return '#9d1c21';if(reference.state==='ready')return '#16803c';if(reference.state==='collecting_reference_frames')return '#a46a00';return '#9d1c21';}
function renderReference(reference){
  referenceOutput.textContent=reference?JSON.stringify(reference,null,2):'reference mode is not active';overlay.innerHTML='';if(!reference)return;
  const color=markerColor(reference), markers=reference.marker_corners_uv||{};
  for(const corners of Object.values(markers)){if(!Array.isArray(corners)||corners.length!==4)continue;const points=corners.map(point=>point.u+','+point.v).join(' ');const polygon=document.createElementNS('http://www.w3.org/2000/svg','polygon');polygon.setAttribute('points',points);polygon.setAttribute('stroke',color);overlay.appendChild(polygon);}
}
function renderTargetCoordinate(state){
  const coordinate=state.machine_xy_mm, hasCoordinate=state.state==='ready'&&state.mapping_state==='available'&&coordinate&&Number.isFinite(Number(coordinate.x))&&Number.isFinite(Number(coordinate.y));
  if(hasCoordinate){coordinateX.textContent=formatCoordinate(coordinate.x);coordinateY.textContent=formatCoordinate(coordinate.y);coordinateState.textContent='实时红方块坐标';coordinateCard.dataset.state='ready';return;}
  coordinateX.textContent='--';coordinateY.textContent='--';coordinateState.textContent=state.state==='no_target'?'未检测到有效红方块':'坐标不可用';coordinateCard.dataset.state='unavailable';
}
function formatCoordinate(value){const number=Number(value);return (number>=0?'+':'')+number.toFixed(2);}
async function refresh(){
  try{
    const response=await fetch('/state.json',{cache:'no-store'}); const state=await response.json();
    output.textContent=JSON.stringify(state,null,2); renderTargetCoordinate(state); renderReference(state.reference); frame.src='/frame.bmp?t='+Date.now();
    const b=state.target&&state.target.bbox_uvwh;
    if(b){const scale=stage.clientWidth/DISPLAY_WIDTH;box.style.display='block';box.style.left=(b.u*scale)+'px';box.style.top=(b.v*scale)+'px';box.style.width=(b.width*scale)+'px';box.style.height=(b.height*scale)+'px';}
    else{box.style.display='none';}
  }catch(error){renderTargetCoordinate({});output.textContent='dashboard refresh failed: '+error;}
}
refresh();setInterval(refresh,250);
</script></body></html>"""


if __name__ == "__main__":
    raise SystemExit(main())
