"""A small desktop launcher for the DayuWriter visual-follow demonstration."""

from __future__ import annotations

import json
import math
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk
from typing import Any, Mapping
from urllib.error import URLError
from urllib.request import urlopen

import pyrealsense2 as rs
from serial.tools import list_ports

from .grbl_controller import GrblController
from .grbl_protocol import JogCommand, validate_jog
from .workspace import split_delta


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PORT = 8765
DASHBOARD_URL = f"http://127.0.0.1:{DASHBOARD_PORT}/"
STATE_URL = f"{DASHBOARD_URL}state.json"
READY_TIMEOUT_SECONDS = 90.0
CALIBRATION_MOVES = {
    "X+30": ("X", 30.0),
    "X-30": ("X", -30.0),
    "Y+30": ("Y", 30.0),
    "Y-30": ("Y", -30.0),
}


class LauncherError(ValueError):
    """Raised when the launcher cannot prove that a safe software state exists."""


def parse_p0_baseline(payload: Mapping[str, Any]) -> tuple[float, float]:
    """Return a current P0 visual baseline only from a strict ready dashboard state."""

    if payload.get("state") != "ready" or payload.get("mapping_state") != "available":
        raise LauncherError("visual page is not ready")
    if payload.get("motion_permission") != "display_only":
        raise LauncherError("visual page has an unexpected permission state")
    if not isinstance(payload.get("target"), Mapping):
        raise LauncherError("no current red square is detected")
    machine_xy = payload.get("machine_xy_mm")
    if not isinstance(machine_xy, Mapping):
        raise LauncherError("the red square has no paper coordinate")
    try:
        x_mm = float(machine_xy["x"])
        y_mm = float(machine_xy["y"])
    except (KeyError, TypeError, ValueError) as exc:
        raise LauncherError("the paper coordinate is invalid") from exc
    if not math.isfinite(x_mm) or not math.isfinite(y_mm):
        raise LauncherError("the paper coordinate is invalid")
    return x_mm, y_mm


def build_dashboard_command(python: str, camera_serial: str) -> list[str]:
    """Build the display-only camera command; it has no serial-port argument."""

    return [
        python,
        "-m",
        "vision.realsense.live_red_target_dashboard",
        "--serial",
        camera_serial,
        "--aruco-reference-board",
        "--reference-registration",
        "docs/dayuwriter/calibration/camera-a-a4-aruco-registration.json",
        "--port",
        str(DASHBOARD_PORT),
    ]


def build_follow_command(
    *,
    python: str,
    port: str,
    baseline: tuple[float, float],
    dashboard_url: str,
) -> list[str]:
    """Build the continuous XY-only command used after the operator arms P0."""

    x_mm, y_mm = baseline
    return [
        python,
        "-m",
        "communication.dayuwriter.visual_follow",
        "--dashboard-url",
        dashboard_url,
        "--port",
        port,
        "--baseline-x",
        f"{x_mm:.6f}",
        "--baseline-y",
        f"{y_mm:.6f}",
        "--continuous",
        "--wait-for-target-change",
        "--until-stopped",
        "--return-to-p0",
        "--hold-at-target-seconds",
        "10",
        "--feed",
        "500",
        "--execute",
        "--physical-preflight",
    ]


def build_calibration_jog(label: str) -> tuple[JogCommand, ...]:
    """Return one of the four explicit low-speed P0/X30/Y30 verification moves."""

    try:
        axis, total_distance_mm = CALIBRATION_MOVES[label]
    except KeyError as exc:
        raise LauncherError(f"unsupported calibration jog: {label}") from exc
    return tuple(
        validate_jog(JogCommand(axis, segment_mm, 100.0))
        for segment_mm in split_delta(total_distance_mm)
    )


def discover_camera_serials() -> list[str]:
    """Enumerate non-platform RealSense devices without starting a video stream."""

    context = rs.context()
    return [
        device.get_info(rs.camera_info.serial_number)
        for device in context.devices
        if device.get_info(rs.camera_info.name).lower() != "platform camera"
    ]


def discover_ch340_ports() -> list[str]:
    """Find likely CH340 ports using pyserial's Windows port enumeration."""

    matches: list[str] = []
    for port in list_ports.comports():
        identity = f"{port.description} {port.hwid}".upper()
        if "CH340" in identity or "CH341" in identity or "VID:PID=1A86" in identity:
            matches.append(port.device)
    return matches


def fetch_dashboard_state(url: str = STATE_URL) -> Mapping[str, Any]:
    """Read one live dashboard snapshot without accepting browser display caching."""

    try:
        with urlopen(url, timeout=1.0) as response:  # noqa: S310 - loopback-only constant.
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LauncherError(f"visual page unavailable: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise LauncherError("visual page returned an invalid state")
    return payload


class DayuWriterLauncher:
    """Keep child processes observable while presenting a minimal click-based workflow."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.dashboard_process: subprocess.Popen[str] | None = None
        self.follow_process: subprocess.Popen[str] | None = None
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.camera_status = tk.StringVar(value="相机：正在检查")
        self.visual_status = tk.StringVar(value="可视化：未启动")
        self.writer_status = tk.StringVar(value="写字机：正在检查")
        self.follow_status = tk.StringVar(value="自动跟随：未启动")
        self.preflight = tk.BooleanVar(value=False)
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._refresh_devices()
        self.root.after(250, self._drain_events)
        self.root.after(500, self._poll_dashboard)

    def _build_ui(self) -> None:
        self.root.title("DayuWriter")
        self.root.minsize(660, 500)
        self.root.configure(background="#f4f5f3")

        style = ttk.Style(self.root)
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 18, "bold"))
        style.configure("Status.TLabel", font=("Microsoft YaHei UI", 10))
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 11, "bold"), padding=(12, 8))
        style.configure("Action.TButton", font=("Microsoft YaHei UI", 10), padding=(10, 7))

        outer = ttk.Frame(self.root, padding=20)
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        ttk.Label(outer, text="DayuWriter", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        status = ttk.Frame(outer, padding=(0, 14, 0, 10))
        status.grid(row=1, column=0, sticky="ew")
        for row, variable in enumerate(
            (self.camera_status, self.visual_status, self.writer_status, self.follow_status)
        ):
            ttk.Label(status, textvariable=variable, style="Status.TLabel").grid(
                row=row, column=0, sticky="w", pady=2
            )

        ttk.Button(
            outer,
            text="启动可视化",
            style="Action.TButton",
            command=self._start_dashboard,
        ).grid(row=2, column=0, sticky="ew", pady=(4, 8))
        ttk.Checkbutton(
            outer,
            text="已确认：笔尖在 P0，红方块在 P0，12 V 已接通，笔尖悬空，路径净空",
            variable=self.preflight,
        ).grid(row=3, column=0, sticky="w", pady=(6, 8))
        calibration = ttk.Frame(outer)
        calibration.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        for column, label in enumerate(("X+30", "X-30", "Y+30", "Y-30")):
            calibration.columnconfigure(column, weight=1)
            ttk.Button(
                calibration,
                text=label,
                style="Action.TButton",
                command=lambda current_label=label: self._run_calibration_jog(current_label),
            ).grid(row=0, column=column, sticky="ew", padx=3)
        ttk.Button(
            outer,
            text="从 P0 启动自动跟随",
            style="Primary.TButton",
            command=self._start_auto_follow,
        ).grid(row=5, column=0, sticky="ew", pady=(0, 8))
        controls = ttk.Frame(outer)
        controls.grid(row=6, column=0, sticky="ew", pady=(0, 12))
        for column in range(3):
            controls.columnconfigure(column, weight=1)
        ttk.Button(controls, text="停止自动跟随", style="Action.TButton", command=self._stop_follow).grid(
            row=0, column=0, sticky="ew", padx=(0, 6)
        )
        ttk.Button(controls, text="停止可视化", style="Action.TButton", command=self._stop_dashboard).grid(
            row=0, column=1, sticky="ew", padx=3
        )
        ttk.Button(controls, text="打开标定手册", style="Action.TButton", command=self._open_calibration).grid(
            row=0, column=2, sticky="ew", padx=(6, 0)
        )

        self.log = scrolledtext.ScrolledText(
            outer,
            height=9,
            wrap=tk.WORD,
            font=("Consolas", 9),
            state="disabled",
        )
        self.log.grid(row=7, column=0, sticky="nsew")
        outer.rowconfigure(7, weight=1)

    def _refresh_devices(self) -> None:
        try:
            cameras = discover_camera_serials()
            self.camera_status.set(
                f"相机：{', '.join(cameras)}" if cameras else "相机：未发现 D435i"
            )
        except Exception as exc:  # pragma: no cover - depends on Windows USB runtime.
            self.camera_status.set(f"相机：检测失败 ({exc})")
        ports = discover_ch340_ports()
        self.writer_status.set(
            f"写字机：{ports[0]}" if len(ports) == 1 else "写字机：未发现唯一 CH340"
        )

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert(tk.END, f"{message}\n")
        self.log.see(tk.END)
        self.log.configure(state="disabled")

    def _drain_events(self) -> None:
        while True:
            try:
                category, message = self.events.get_nowait()
            except queue.Empty:
                break
            self._append_log(message)
            if category == "visual":
                self.visual_status.set(message)
            elif category == "follow":
                self.follow_status.set(message)
            elif category == "calibration":
                self.writer_status.set(message)
        self.root.after(250, self._drain_events)

    def _start_process(self, command: list[str], category: str) -> subprocess.Popen[str]:
        process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        threading.Thread(
            target=self._stream_process_output,
            args=(process, category),
            daemon=True,
        ).start()
        return process

    def _stream_process_output(self, process: subprocess.Popen[str], category: str) -> None:
        if process.stdout is not None:
            for line in process.stdout:
                line = line.strip()
                if line:
                    self.events.put((category, line))
        exit_code = process.wait()
        if category == "follow":
            self.events.put((category, f"自动跟随已停止 (exit {exit_code})"))
        elif exit_code != 0:
            self.events.put((category, f"可视化进程已退出 (exit {exit_code})"))

    def _start_dashboard(self) -> bool:
        if self.dashboard_process is not None and self.dashboard_process.poll() is None:
            self.visual_status.set("可视化：已启动")
            webbrowser.open(DASHBOARD_URL)
            return True
        try:
            state = fetch_dashboard_state()
        except LauncherError:
            state = None
        if state is not None:
            self.visual_status.set("可视化：已有页面")
            webbrowser.open(DASHBOARD_URL)
            return True
        cameras = discover_camera_serials()
        if len(cameras) != 1:
            self.camera_status.set("相机：需要只连接一台 D435i")
            return False
        self.dashboard_process = self._start_process(
            build_dashboard_command(sys.executable, cameras[0]), "visual"
        )
        self.visual_status.set("可视化：正在启动")
        webbrowser.open(DASHBOARD_URL)
        return True

    def _start_auto_follow(self) -> None:
        if not self.preflight.get():
            self.follow_status.set("自动跟随：请先勾选现场确认")
            return
        if self.follow_process is not None and self.follow_process.poll() is None:
            self.follow_status.set("自动跟随：已经运行")
            return
        if not self._start_dashboard():
            return
        ports = discover_ch340_ports()
        if len(ports) != 1:
            self.writer_status.set("写字机：需要只连接一个 CH340")
            return
        self.follow_status.set("自动跟随：等待 P0 红方块和可视化 ready")
        threading.Thread(target=self._wait_then_start_follow, args=(ports[0],), daemon=True).start()

    def _run_calibration_jog(self, label: str) -> None:
        if not self.preflight.get():
            self.writer_status.set("写字机：请先勾选现场确认")
            return
        if self.follow_process is not None and self.follow_process.poll() is None:
            self.writer_status.set("写字机：停止自动跟随后才能校准移动")
            return
        ports = discover_ch340_ports()
        if len(ports) != 1:
            self.writer_status.set("写字机：需要只连接一个 CH340")
            return
        commands = build_calibration_jog(label)
        self.writer_status.set(f"写字机：正在执行 {label}")
        threading.Thread(
            target=self._execute_calibration_jog,
            args=(ports[0], label, commands),
            daemon=True,
        ).start()

    def _execute_calibration_jog(
        self, port: str, label: str, commands: tuple[JogCommand, ...]
    ) -> None:
        try:
            with GrblController(port) as controller:
                for command in commands:
                    controller.jog(command)
        except Exception as exc:  # pragma: no cover - depends on physical serial hardware.
            self.events.put(("calibration", f"校准移动 {label} 失败：{exc}"))
            return
        self.events.put(("calibration", f"校准移动 {label} 完成；检查笔尖位置后再继续"))

    def _wait_then_start_follow(self, port: str) -> None:
        deadline = time.monotonic() + READY_TIMEOUT_SECONDS
        last_error = ""
        while time.monotonic() < deadline:
            try:
                baseline = parse_p0_baseline(fetch_dashboard_state())
            except LauncherError as exc:
                last_error = str(exc)
                time.sleep(0.5)
                continue
            command = build_follow_command(
                python=sys.executable,
                port=port,
                baseline=baseline,
                dashboard_url=STATE_URL,
            )
            self.follow_process = self._start_process(command, "follow")
            self.events.put(
                ("follow", f"自动跟随：已武装 P0 X={baseline[0]:.3f} mm, Y={baseline[1]:.3f} mm")
            )
            return
        self.events.put(("follow", f"自动跟随未启动：{last_error or '等待超时'}"))

    def _stop_follow(self) -> None:
        if self.follow_process is None or self.follow_process.poll() is not None:
            self.follow_status.set("自动跟随：未运行")
            return
        self.follow_process.terminate()
        self.follow_status.set("自动跟随：正在停止；检查笔尖后重新对准 P0")

    def _stop_dashboard(self) -> None:
        if self.follow_process is not None and self.follow_process.poll() is None:
            self._stop_follow()
        if self.dashboard_process is None or self.dashboard_process.poll() is not None:
            self.visual_status.set("可视化：未由本窗口启动")
            return
        self.dashboard_process.terminate()
        self.visual_status.set("可视化：正在停止")

    def _open_calibration(self) -> None:
        guide = PROJECT_ROOT / "docs" / "dayuwriter" / "29-simple-calibration-guide.md"
        webbrowser.open(guide.as_uri())

    def _poll_dashboard(self) -> None:
        try:
            state = fetch_dashboard_state()
            if state.get("state") == "ready" and state.get("mapping_state") == "available":
                self.visual_status.set("可视化：ready")
            else:
                self.visual_status.set(f"可视化：{state.get('state', '未知')}")
        except LauncherError:
            if self.dashboard_process is None or self.dashboard_process.poll() is not None:
                self.visual_status.set("可视化：未启动")
        self.root.after(500, self._poll_dashboard)

    def _on_close(self) -> None:
        follow_running = self.follow_process is not None and self.follow_process.poll() is None
        if follow_running and not messagebox.askyesno(
            "DayuWriter", "自动跟随仍在运行。停止后笔尖可能不在 P0，确定退出吗？"
        ):
            return
        if follow_running:
            self.follow_process.terminate()
        if self.dashboard_process is not None and self.dashboard_process.poll() is None:
            self.dashboard_process.terminate()
        self.root.destroy()


def main() -> int:
    root = tk.Tk()
    DayuWriterLauncher(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
