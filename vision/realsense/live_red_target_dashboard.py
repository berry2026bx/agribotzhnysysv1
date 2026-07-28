"""Loopback-only D435i red-target coordinate display with no GRBL access."""

from __future__ import annotations

import argparse
import json
import math
import struct
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import numpy as np

from .red_target import (
    RedTarget,
    RedTargetConfig,
    RedTargetError,
    TargetObservation,
    find_red_target,
    observe_target,
)


COLOR_WIDTH = 640
COLOR_HEIGHT = 480
FRAME_RATE = 30


class DashboardError(RuntimeError):
    """Raised for invalid dashboard configuration or camera failures."""


@dataclass(frozen=True)
class Calibration:
    serial: str
    pixel_to_machine: np.ndarray | None


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
) -> dict[str, Any]:
    """Serialize the current display-only camera result for the browser."""
    state: dict[str, Any] = {
        "motion_permission": "display_only",
        "error": error,
    }
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
) -> None:
    """Read D435i frames until stopped and publish the latest display snapshot."""
    try:
        import pyrealsense2 as rs

        pipeline = rs.pipeline()
        config = rs.config()
        config.enable_device(calibration.serial)
        config.enable_stream(rs.stream.depth, COLOR_WIDTH, COLOR_HEIGHT, rs.format.z16, FRAME_RATE)
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
            target = find_red_target(rgb, target_config)
            if target is None:
                store.publish(make_bmp_bytes(rgb), snapshot_state(None, None, error=None))
                continue
            try:
                color_profile = color_frame.profile.as_video_stream_profile()
                observation = observe_target(
                    target,
                    depth_frame=depth_frame,
                    color_intrinsics=color_profile.get_intrinsics(),
                    deproject=rs.rs2_deproject_pixel_to_point,
                    pixel_to_machine=calibration.pixel_to_machine,
                    width=int(color_profile.width()),
                    height=int(color_profile.height()),
                    depth_sample_radius=depth_sample_radius,
                )
            except RedTargetError as exc:
                store.publish(make_bmp_bytes(rgb), snapshot_state(target, None, error=str(exc)))
                continue
            store.publish(make_bmp_bytes(rgb), snapshot_state(target, observation, error=None))
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
        calibration = (
            Calibration(serial=args.serial, pixel_to_machine=None)
            if args.camera_xyz_only
            else load_calibration(args.calibration, args.serial)
        )
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
            },
            name="d435i-red-target",
            daemon=True,
        )
        server = ThreadingHTTPServer(("127.0.0.1", args.port), _make_handler(store))
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


def _make_handler(store: SnapshotStore) -> type[BaseHTTPRequestHandler]:
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

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_bytes(self, payload: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
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
main{display:grid;grid-template-columns:640px minmax(280px,1fr);gap:20px;padding:20px}
#stage{position:relative;width:640px;height:480px;background:#171d18}
#frame{display:block;width:640px;height:480px}
#box{position:absolute;border:3px solid #d61f26;display:none;box-sizing:border-box}
section{background:#fff;border:1px solid #ccd3ca;padding:16px;max-width:440px}
h1{font-size:20px;margin:0 0 16px}pre{white-space:pre-wrap;word-break:break-word;margin:0;font-size:14px}
.warn{color:#9d1c21;font-weight:700}
</style></head><body><main><div id="stage"><img id="frame" alt="Live D435i RGB"><div id="box"></div></div>
<section><h1>Display-only red target</h1><p class="warn">No GRBL motion is available in this page.</p><pre id="state">starting</pre></section></main>
<script>
const frame=document.getElementById('frame'), box=document.getElementById('box'), output=document.getElementById('state');
async function refresh(){
  try{
    const response=await fetch('/state.json',{cache:'no-store'}); const state=await response.json();
    output.textContent=JSON.stringify(state,null,2); frame.src='/frame.bmp?t='+Date.now();
    const b=state.target&&state.target.bbox_uvwh;
    if(b){box.style.display='block';box.style.left=b.u+'px';box.style.top=b.v+'px';box.style.width=b.width+'px';box.style.height=b.height+'px';}
    else{box.style.display='none';}
  }catch(error){output.textContent='dashboard refresh failed: '+error;}
}
refresh();setInterval(refresh,250);
</script></body></html>"""


if __name__ == "__main__":
    raise SystemExit(main())
