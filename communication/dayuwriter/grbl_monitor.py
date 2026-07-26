from __future__ import annotations

import argparse
import queue
import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import scrolledtext, ttk

from .grbl_controller import ControllerError, GrblController, TraceEvent
from .grbl_protocol import JogCommand
from .workspace import parse_mpos, validate_xy_target


BUTTON_ACTIONS: dict[str, tuple[str, float, float]] = {
    "X 向左 -5 mm": ("X", -5.0, 100.0),
    "X 向右 +5 mm": ("X", 5.0, 100.0),
    "Y 向后 -5 mm": ("Y", -5.0, 100.0),
    "Y 向前 +5 mm": ("Y", 5.0, 100.0),
    "Z 向上 -1 mm": ("Z", -1.0, 50.0),
    "Z 向下 +1 mm": ("Z", 1.0, 50.0),
}


def format_trace_event(event: TraceEvent) -> tuple[str, str]:
    """Return presentation text without changing the underlying trace."""

    if event.kind == "CALL":
        return "PYTHON", f"调用 {event.text}"
    if event.kind == "TX":
        return "TX → GRBL", event.text
    if event.kind == "RX":
        return "GRBL → RX", event.text
    return event.kind, event.text


def validate_monitor_motion(status_raw: str, axis: str, distance_mm: float) -> None:
    """Apply the established P0 XY envelope before a monitor button jog."""

    axis = axis.upper()
    if axis not in {"X", "Y", "Z"}:
        raise ValueError(f"unsupported axis: {axis!r}")
    if axis == "Z":
        return
    position = parse_mpos(status_raw)
    target_x = position.x + distance_mm if axis == "X" else position.x
    target_y = position.y + distance_mm if axis == "Y" else position.y
    validate_xy_target(target_x, target_y)


class GrblWorker:
    """Own the serial connection in one worker thread."""

    def __init__(
        self,
        port: str,
        events: queue.Queue[tuple[str, object]],
        *,
        controller_factory: Callable[..., GrblController] = GrblController,
    ) -> None:
        self._port = port
        self._events = events
        self._controller_factory = controller_factory
        self._commands: queue.Queue[tuple[str, object | None]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._last_status_raw: str | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._thread = threading.Thread(target=self._run, name="dayuwriter-grbl", daemon=True)
        self._thread.start()

    def request_status(self) -> None:
        self._commands.put(("status", None))

    def request_jog(self, axis: str, distance_mm: float, feed_mm_min: float) -> None:
        self._commands.put(("jog", JogCommand(axis, distance_mm, feed_mm_min)))

    def stop(self) -> None:
        self._commands.put(("stop", None))

    def _run(self) -> None:
        controller = self._controller_factory(
            self._port,
            trace_sink=lambda event: self._events.put(("trace", event)),
        )
        try:
            controller.open()
            self._events.put(("connected", self._port))
            initial_status = controller.status().raw
            self._last_status_raw = initial_status
            self._events.put(("status", initial_status))
            while True:
                kind, payload = self._commands.get()
                if kind == "stop":
                    return
                try:
                    if kind == "status":
                        status = controller.status().raw
                        self._last_status_raw = status
                        self._events.put(("status", status))
                    elif kind == "jog":
                        if self._last_status_raw is None:
                            self._last_status_raw = controller.status().raw
                        validate_monitor_motion(
                            self._last_status_raw,
                            payload.axis,
                            payload.distance_mm,
                        )
                        result = controller.jog(payload)
                        self._last_status_raw = result.final_status.raw
                        self._events.put(("status", result.final_status.raw))
                        self._events.put(("motion_done", result.command))
                except (ControllerError, OSError, ValueError) as exc:
                    self._events.put(("error", str(exc)))
        except (ControllerError, OSError) as exc:
            self._events.put(("error", str(exc)))
        finally:
            try:
                controller.close()
            except ControllerError as exc:
                self._events.put(("error", str(exc)))
            self._events.put(("disconnected", None))


class ProtocolMonitorApp:
    def __init__(self, root: tk.Tk, port: str) -> None:
        self._root = root
        self._port = port
        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._worker: GrblWorker | None = None
        self._motion_buttons: list[ttk.Button] = []

        self._root.title("DayuWriter 真实 GRBL 通信监视器")
        self._root.minsize(980, 650)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._state = tk.StringVar(value="未连接：点击“连接 COM3”后开始真实串口通信")
        self._build_ui()
        self._root.after(100, self._drain_events)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self._root, padding=12)
        outer.grid(sticky="nsew")
        self._root.columnconfigure(0, weight=1)
        self._root.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(3, weight=1)

        ttk.Label(
            outer,
            text="Python → COM3 → GRBL → A4988 → 真实步进电机",
            font=("Microsoft YaHei UI", 15, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        ttk.Label(outer, textvariable=self._state).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))

        controls = ttk.LabelFrame(outer, text="真实机器控制（每次仅发送受限微动）", padding=8)
        controls.grid(row=2, column=0, sticky="nsew", padx=(0, 6), pady=(0, 8))
        trace = ttk.LabelFrame(outer, text="实际 Python 调用链", padding=8)
        trace.grid(row=2, column=1, sticky="nsew", padx=(6, 0), pady=(0, 8))

        self._connect_button = ttk.Button(controls, text=f"连接 {self._port}", command=self._connect)
        self._connect_button.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self._status_button = ttk.Button(controls, text="读取状态 ?（不移动）", command=self._status, state="disabled")
        self._status_button.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        for index, (label, action) in enumerate(BUTTON_ACTIONS.items()):
            button = ttk.Button(
                controls,
                text=label,
                command=lambda move=action: self._jog(*move),
                state="disabled",
            )
            button.grid(row=2 + index // 2, column=index % 2, sticky="ew", padx=3, pady=3)
            self._motion_buttons.append(button)
        controls.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=1)

        ttk.Label(
            trace,
            text=(
                "按钮点击\n"
                "  ↓\nPython: grbl_monitor.py\n"
                "  ↓\nPython: GrblController.jog()\n"
                "  ↓\npySerial: COM3 (115200, 8-N-1)\n"
                "  ↓\nArduino: GRBL 1.1f\n"
                "  ↓\nCNC V3 + A4988 → 电机"
            ),
            justify="left",
        ).grid(sticky="nw")

        protocol = ttk.LabelFrame(outer, text="真实串口协议记录（不是模拟）", padding=8)
        protocol.grid(row=3, column=0, columnspan=2, sticky="nsew")
        protocol.columnconfigure(0, weight=1)
        protocol.rowconfigure(0, weight=1)
        self._log = scrolledtext.ScrolledText(protocol, height=20, wrap="word", state="disabled", font=("Consolas", 10))
        self._log.grid(sticky="nsew")
        self._log.tag_configure("CALL", foreground="#005cc5")
        self._log.tag_configure("TX", foreground="#8a3b00")
        self._log.tag_configure("RX", foreground="#0b6b2d")
        self._log.tag_configure("ERROR", foreground="#b00020")

    def _connect(self) -> None:
        if self._worker is not None and self._worker.is_running:
            return
        self._state.set(f"正在连接 {self._port}；连接本身不发送运动命令")
        self._connect_button.configure(state="disabled")
        self._worker = GrblWorker(self._port, self._events)
        self._worker.start()

    def _status(self) -> None:
        if self._worker is not None:
            self._worker.request_status()

    def _jog(self, axis: str, distance_mm: float, feed_mm_min: float) -> None:
        if self._worker is not None:
            self._state.set(f"请求真实运动：{axis}{distance_mm:g} mm，F{feed_mm_min:g}")
            self._worker.request_jog(axis, distance_mm, feed_mm_min)

    def _drain_events(self) -> None:
        while True:
            try:
                kind, payload = self._events.get_nowait()
            except queue.Empty:
                break
            if kind == "trace":
                label, text = format_trace_event(payload)
                tag = {"PYTHON": "CALL", "TX → GRBL": "TX", "GRBL → RX": "RX"}.get(label, "CALL")
                self._append_log(f"[{label}] {text}", tag)
            elif kind == "connected":
                self._state.set(f"已连接 {payload}：现在可观察真实协议或点击受限微动")
                self._status_button.configure(state="normal")
                for button in self._motion_buttons:
                    button.configure(state="normal")
            elif kind == "status":
                self._state.set(f"GRBL 状态：{payload}")
                self._append_log(f"[状态] {payload}", "RX")
            elif kind == "motion_done":
                command = payload
                self._state.set(f"真实运动完成：{command.axis}{command.distance_mm:g} mm")
            elif kind == "error":
                self._state.set(f"错误：{payload}")
                self._append_log(f"[错误] {payload}", "ERROR")
            elif kind == "disconnected":
                self._status_button.configure(state="disabled")
                for button in self._motion_buttons:
                    button.configure(state="disabled")
                if self._worker is not None and not self._worker.is_running:
                    self._connect_button.configure(state="normal")
        self._root.after(100, self._drain_events)

    def _append_log(self, text: str, tag: str) -> None:
        self._log.configure(state="normal")
        self._log.insert("end", text + "\n", tag)
        self._log.see("end")
        self._log.configure(state="disabled")

    def _on_close(self) -> None:
        if self._worker is not None and self._worker.is_running:
            self._worker.stop()
            self._root.after(150, self._root.destroy)
            return
        self._root.destroy()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Live DayuWriter GRBL protocol monitor")
    parser.add_argument("--port", required=True, help="Live-discovered Windows COM port")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = tk.Tk()
    ProtocolMonitorApp(root, args.port)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
