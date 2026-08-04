"""Display-only D435i + YOLO dashboard; it never opens a GRBL port."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

import cv2
import numpy as np

from .aruco_pose import BoardPose, estimate_board_pose, validate_board_pose
from .aruco_reference_board import BoardRegistrationError, default_layout, load_registration
from .aruco_plane_calibration import detect_marker_corners
from .object_localization import CameraPoint, MachinePoint, deproject_color_pixel, estimate_depth_m, transform_camera_to_writer
from ..yolo.detector import Detection, DetectorConfig, YoloDetector, select_target


class DashboardError(RuntimeError):
    pass


def snapshot_yolo_state(
    *,
    serial: str,
    detection: Detection | None,
    camera_point: CameraPoint | None,
    machine_point: MachinePoint | None,
    board_pose: BoardPose | None,
    error: str | None,
) -> dict[str, Any]:
    """Serialize one dashboard state; coordinate fields are omitted if invalid."""

    state: dict[str, Any] = {
        "state": "ready" if detection is not None and camera_point is not None and machine_point is not None else ("depth_invalid" if detection is not None else "no_target"),
        "motion_permission": "display_only",
        "mapping_state": "available" if board_pose is not None and machine_point is not None else "unavailable",
        "reference_state": "ready" if board_pose is not None else "unavailable",
        "camera": {"serial": serial},
        "error": error,
    }
    if board_pose is not None:
        state["pose_validation"] = {
            "visible_ids": list(board_pose.visible_ids),
            "reprojection_error_px": board_pose.reprojection_error_px,
            "board_revision": board_pose.board_revision,
        }
    if detection is not None:
        target: dict[str, Any] = {
            "class_id": detection.class_id,
            "class_name": detection.class_name,
            "confidence": detection.confidence,
            "bbox_xyxy": list(detection.xyxy),
            "pixel_center_uv": {"u": detection.center_uv[0], "v": detection.center_uv[1]},
        }
        if camera_point is not None:
            target["camera_xyz_mm"] = {"x": camera_point.x_mm, "y": camera_point.y_mm, "z": camera_point.z_mm}
        if machine_point is not None:
            target["machine_xyz_mm"] = {"x": machine_point.x_mm, "y": machine_point.y_mm, "z": machine_point.z_mm}
            target["machine_xy_mm"] = {"x": machine_point.x_mm, "y": machine_point.y_mm}
            state["machine_xy_mm"] = {"x": machine_point.x_mm, "y": machine_point.y_mm}
        state["target"] = target
    return state


def annotate_yolo_frame(
    rgb: np.ndarray,
    detection: Detection | None,
    machine_xy: dict[str, float] | None,
) -> np.ndarray:
    """Draw a red box and white coordinate label on a copied RGB frame."""

    image = np.asarray(rgb).copy()
    if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
        raise ValueError("rgb must be uint8 HxWx3")
    if detection is None:
        return image
    x1, y1, x2, y2 = [int(round(value)) for value in detection.xyxy]
    cv2.rectangle(image, (x1, y1), (x2, y2), (220, 30, 35), 2)
    text = f"{detection.class_name} {detection.confidence:.2f}"
    if machine_xy is not None and all(math.isfinite(float(machine_xy[key])) for key in ("x", "y")):
        text += f" | X {machine_xy['x']:.0f} Y {machine_xy['y']:.0f} mm"
    (tw, th), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    label_x = max(0, min(image.shape[1] - tw - 8, x2 + 8))
    label_y = max(th + baseline + 4, min(image.shape[0] - 2, y1 + th + baseline + 4))
    cv2.rectangle(image, (label_x, label_y - th - baseline - 4), (label_x + tw + 8, label_y + 2), (255, 255, 255), -1)
    cv2.rectangle(image, (label_x, label_y - th - baseline - 4), (label_x + tw + 8, label_y + 2), (220, 30, 35), 1)
    cv2.putText(image, text, (label_x + 4, label_y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (45, 55, 50), 1, cv2.LINE_AA)
    return image


def make_bmp_bytes(rgb: np.ndarray) -> bytes:
    """Encode RGB data as a 24-bit uncompressed BMP."""

    image = np.asarray(rgb, dtype=np.uint8)
    height, width = image.shape[:2]
    row_bytes, padding = width * 3, (-width * 3) % 4
    payload = b"".join(row.tobytes() + b"\x00" * padding for row in image[::-1, :, ::-1])
    header = b"BM" + (54 + len(payload)).to_bytes(4, "little") + b"\x00\x00\x00\x00\x36\x00\x00\x00"
    dib = (40).to_bytes(4, "little") + int(width).to_bytes(4, "little") + int(height).to_bytes(4, "little", signed=True) + b"\x01\x00\x18\x00" + b"\x00\x00\x00\x00" + len(payload).to_bytes(4, "little") + b"\x13\x0b\x00\x00\x13\x0b\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    return header + dib + payload


class SnapshotStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame = make_bmp_bytes(np.zeros((1, 1, 3), dtype=np.uint8))
        self._state: dict[str, Any] = {"state": "starting", "motion_permission": "display_only", "error": None}

    def publish(self, frame_bmp: bytes, state: dict[str, Any]) -> None:
        with self._lock:
            self._frame, self._state = frame_bmp, state

    def read(self) -> tuple[bytes, dict[str, Any]]:
        with self._lock:
            return self._frame, dict(self._state)


def _handler(store: SnapshotStore) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            frame, state = store.read()
            if path == "/":
                self._send(_html_page().encode(), "text/html; charset=utf-8")
            elif path == "/frame.bmp":
                self._send(frame, "image/bmp")
            elif path == "/state.json":
                self._send(json.dumps(state).encode(), "application/json; charset=utf-8")
            else:
                self.send_error(404)

        def log_message(self, *_args: object) -> None:
            return

        def _send(self, body: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def _html_page() -> str:
    return """<!doctype html><html><head><meta charset='utf-8'><title>D435i YOLO</title><style>body{font:16px Arial;margin:20px;background:#f4f5f3;color:#202820}main{display:grid;grid-template-columns:minmax(0,2fr) minmax(300px,1fr);gap:20px}#stage{position:relative;background:#182019}#frame{width:100%;display:block}.panel{background:#fff;border:1px solid #ccd3ca;padding:16px}.value{font-size:24px;font-weight:700;font-variant-numeric:tabular-nums}pre{white-space:pre-wrap}</style></head><body><main><div id='stage'><img id='frame' alt='D435i RGB frame'></div><div class='panel'><h2>YOLO 目标</h2><div id='summary'>等待检测</div><pre id='state'>starting</pre><p>本页仅显示，不直接打开 GRBL 串口。</p></div></main><script>async function refresh(){try{const s=await (await fetch('/state.json',{cache:'no-store'})).json();document.getElementById('state').textContent=JSON.stringify(s,null,2);const t=s.target;document.getElementById('summary').innerHTML=t?'<div class="value">'+t.class_name+' '+(t.confidence*100).toFixed(1)+'%</div><div>像素: ('+t.pixel_center_uv.u.toFixed(0)+', '+t.pixel_center_uv.v.toFixed(0)+')</div><div>机器XY: '+(t.machine_xy_mm?Math.round(t.machine_xy_mm.x)+', '+Math.round(t.machine_xy_mm.y):'--')+' mm</div>':'等待有效目标';document.getElementById('frame').src='/frame.bmp?t='+Date.now();}catch(e){document.getElementById('summary').textContent='页面连接失败: '+e}}refresh();setInterval(refresh,250);</script></body></html>"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Display-only D435i YOLO dashboard")
    parser.add_argument("--serial", required=True)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--class-name", required=True)
    parser.add_argument("--confidence", type=float, default=0.5)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--warmup-frames", type=int, default=30)
    parser.add_argument(
        "--reference-registration",
        type=Path,
        default=Path("docs/dayuwriter/calibration/camera-a-a4-aruco-registration.json"),
        help="Operator-confirmed fixed P0/ArUco registration record",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        detector = YoloDetector(DetectorConfig(str(args.model), confidence=args.confidence))
        registration = load_registration(args.reference_registration, default_layout())
    except (RuntimeError, ValueError) as exc:
        print(f"YOLO dashboard failed: {exc}")
        return 1
    except BoardRegistrationError as exc:
        print(f"YOLO dashboard failed: reference registration invalid: {exc}")
        return 1
    store = SnapshotStore()
    stop_event = threading.Event()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), _handler(store))
    worker = threading.Thread(target=_camera_worker, args=(store, stop_event, detector, args.serial, args.class_name, args.warmup_frames, registration), daemon=True)
    worker.start()
    print(f"YOLO display-only dashboard: http://127.0.0.1:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set(); server.shutdown(); server.server_close(); worker.join(timeout=5)
    return 0


def _camera_worker(store: SnapshotStore, stop_event: threading.Event, detector: YoloDetector, serial: str, class_name: str, warmup_frames: int, registration: dict[str, object]) -> None:
    try:
        import pyrealsense2 as rs
        pipeline = rs.pipeline(); config = rs.config(); config.enable_device(serial)
        config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
        config.enable_stream(rs.stream.color, 1280, 720, rs.format.rgb8, 30)
        profile = pipeline.start(config); align = rs.align(rs.stream.color)
        for _ in range(max(0, warmup_frames)): pipeline.wait_for_frames()
        layout = default_layout()
        if registration.get("operator_confirmed") is not True:
            raise ValueError("reference registration is not operator-confirmed")
        previous_pose: BoardPose | None = None
        while not stop_event.is_set():
            frames = align.process(pipeline.wait_for_frames()); color = frames.get_color_frame(); depth = frames.get_depth_frame()
            if not color or not depth: continue
            rgb = np.asanyarray(color.get_data()).copy(); detections = detector.predict(rgb); detection = select_target(detections, class_name)
            if detection is None:
                store.publish(make_bmp_bytes(rgb), snapshot_yolo_state(serial=serial, detection=None, camera_point=None, machine_point=None, board_pose=None, error=None)); continue
            camera_point = None; machine_point = None; error = None; board_pose = None
            try:
                corners = detect_marker_corners(rgb, layout)
                intrinsics = color.profile.as_video_stream_profile().get_intrinsics()
                camera_matrix = np.array([[intrinsics.fx, 0.0, intrinsics.ppx], [0.0, intrinsics.fy, intrinsics.ppy], [0.0, 0.0, 1.0]], dtype=float)
                distortion = np.asarray(intrinsics.coeffs, dtype=float)
                board_pose = estimate_board_pose(corners, camera_matrix, distortion, layout, serial=serial, stream_size=(int(intrinsics.width), int(intrinsics.height)))
                validate_board_pose(board_pose, previous_pose=previous_pose)
                previous_pose = board_pose
                z = estimate_depth_m(depth, round(detection.center_uv[0]), round(detection.center_uv[1]), radius=2)
                camera_point = deproject_color_pixel(intrinsics, z, detection.center_uv, rs.rs2_deproject_pixel_to_point)
                machine_point = transform_camera_to_writer(camera_point, board_pose.rotation, board_pose.translation, layout=layout)
            except Exception as exc:
                error = str(exc)
                board_pose = None
                previous_pose = None if "missing marker" in str(exc) else previous_pose
            label_xy = None if machine_point is None else {"x": machine_point.x_mm, "y": machine_point.y_mm}
            store.publish(make_bmp_bytes(annotate_yolo_frame(rgb, detection, label_xy)), snapshot_yolo_state(serial=serial, detection=detection, camera_point=camera_point, machine_point=machine_point, board_pose=board_pose, error=error))
    except Exception as exc:
        store.publish(make_bmp_bytes(np.zeros((1, 1, 3), dtype=np.uint8)), {"state": "camera_error", "motion_permission": "display_only", "error": f"camera_runtime_failed: {exc}"})
    finally:
        try: pipeline.stop()
        except Exception: pass


if __name__ == "__main__":
    raise SystemExit(main())
