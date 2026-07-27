from __future__ import annotations

import argparse
import queue
import threading
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
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


def event_stage(event: TraceEvent) -> str:
    """Map an observed trace event to one causal-chain stage."""

    if event.kind == "CALL":
        return "python"
    if event.kind == "TX":
        return "poll" if event.text.strip() == "?" else "command"
    if event.kind == "RX":
        if event.text.strip() == "ok":
            return "accepted"
        if event.text.strip().startswith("<"):
            return "complete" if event.text.strip().startswith("<Idle|") else "running"
    return "python"


def describe_trace_event(event: TraceEvent) -> str:
    """Explain a real trace in language suitable for a non-technical observer."""

    stage = event_stage(event)
    return {
        "python": "Python 正在调用持久控制器",
        "command": "Python 已把运动指令写入串口",
        "accepted": "GRBL 已接收指令；这不等于运动完成",
        "poll": "Python 正在询问 GRBL 当前状态",
        "running": "GRBL 报告运动仍在进行",
        "complete": "GRBL 报告 Idle，控制周期已完成",
    }[stage]


@dataclass(frozen=True)
class ChainStage:
    key: str
    title: str
    detail: str


CHAIN_STAGES = (
    ChainStage("python", "Python 调用", "持久控制器接到动作请求"),
    ChainStage("command", "TX 运动指令", "ASCII 写入 COM4"),
    ChainStage("accepted", "RX ok", "GRBL 接收，不代表完成"),
    ChainStage("poll", "TX ?", "读取实时状态"),
    ChainStage("running", "RX Jog", "GRBL 报告运动进行中"),
    ChainStage("complete", "RX Idle", "控制周期完成"),
)


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
    """Teacher-facing live console; all chain updates come from real trace events."""

    BG = "#07111d"
    SURFACE = "#0d1b2a"
    SURFACE_2 = "#11263a"
    BORDER = "#23415a"
    TEXT = "#e8f1f7"
    MUTED = "#8ea6b8"
    GREEN = "#36d399"
    AMBER = "#f4b860"
    BLUE = "#63b3ed"
    RED = "#ff6b6b"

    def __init__(self, root: tk.Tk, port: str) -> None:
        self._root = root
        self._port = port
        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._worker: GrblWorker | None = None
        self._motion_buttons: list[ttk.Button] = []

        self._root.title("DayuWriter · 现场演示台 · 真实 GRBL 串口")
        self._root.minsize(1180, 760)
        self._root.configure(bg=self.BG)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._configure_style()

        self._state = tk.StringVar(value="未连接 · 串口尚未打开 · 不会自动运动")
        self._connection = tk.StringVar(value="OFFLINE")
        self._grbl_state = tk.StringVar(value="—")
        self._position = tk.StringVar(value="MPos  —")
        self._explanation = tk.StringVar(value="点击“连接并读取状态”后，屏幕将只显示真实串口证据。")
        self._last_event = tk.StringVar(value="等待真实 TraceEvent")
        self._build_ui()
        self._root.after(100, self._drain_events)

    def _configure_style(self) -> None:
        style = ttk.Style(self._root)
        style.theme_use("clam")
        style.configure("TFrame", background=self.BG)
        style.configure("Accent.TButton", background="#1d8064", foreground="#ffffff", padding=(14, 9), font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#28a67e"), ("disabled", "#18382f")])
        style.configure("Motion.TButton", background=self.SURFACE_2, foreground=self.TEXT, padding=(10, 8), font=("Microsoft YaHei UI", 10))
        style.map("Motion.TButton", background=[("active", "#1b405b"), ("disabled", "#132332")])

    def _build_ui(self) -> None:
        self._root.columnconfigure(0, weight=1)
        self._root.rowconfigure(0, weight=1)
        outer = ttk.Frame(self._root, padding=18)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        header = tk.Frame(outer, bg=self.BG)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.columnconfigure(1, weight=1)
        tk.Label(header, text="DAYUWRITER / LIVE BENCH", bg=self.BG, fg=self.GREEN, font=("Consolas", 10, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(header, text="真实 GRBL 通信现场演示台", bg=self.BG, fg=self.TEXT, font=("Microsoft YaHei UI", 19, "bold")).grid(row=1, column=0, sticky="w")
        tk.Label(header, text="按钮 → Python → 串口 TX/RX → GRBL → 步进电机", bg=self.BG, fg=self.MUTED, font=("Microsoft YaHei UI", 10)).grid(row=2, column=0, sticky="w")
        meta = tk.Frame(header, bg=self.BG)
        meta.grid(row=0, column=1, rowspan=3, sticky="e")
        self._metric(meta, "PORT", self._port, 0)
        self._metric(meta, "LINK", self._connection, 1)
        self._metric(meta, "GRBL", self._grbl_state, 2)
        self._metric(meta, "POSITION", self._position, 3)

        chain_panel = tk.Frame(outer, bg=self.SURFACE, highlightbackground=self.BORDER, highlightthickness=1)
        chain_panel.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        chain_panel.columnconfigure(0, weight=1)
        tk.Label(chain_panel, text="01 / 因果链 · 每个节点由真实事件点亮", bg=self.SURFACE, fg=self.MUTED, font=("Consolas", 9, "bold")).grid(row=0, column=0, sticky="w", padx=16, pady=(13, 0))
        self._chain = tk.Canvas(chain_panel, height=146, bg=self.SURFACE, bd=0, highlightthickness=0)
        self._chain.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 4))
        self._chain.bind("<Configure>", lambda _event: self._draw_chain())
        tk.Label(chain_panel, textvariable=self._explanation, bg=self.SURFACE, fg=self.AMBER, anchor="w", font=("Microsoft YaHei UI", 10, "bold")).grid(row=2, column=0, sticky="ew", padx=16, pady=(3, 13))

        workspace = ttk.Frame(outer)
        workspace.grid(row=2, column=0, sticky="nsew")
        workspace.columnconfigure(0, weight=0, minsize=290)
        workspace.columnconfigure(1, weight=1, minsize=500)
        workspace.rowconfigure(0, weight=1)
        self._build_controls(workspace)
        self._build_stream(workspace)

        footer = tk.Label(outer, textvariable=self._state, bg=self.BG, fg=self.MUTED, anchor="w", font=("Microsoft YaHei UI", 9))
        footer.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self._draw_chain()

    def _metric(self, parent: tk.Widget, title: str, value: tk.Variable | str, column: int) -> None:
        block = tk.Frame(parent, bg=self.BG)
        block.grid(row=0, column=column, padx=(18 if column else 0, 0), sticky="e")
        tk.Label(block, text=title, bg=self.BG, fg=self.MUTED, font=("Consolas", 8, "bold")).pack(anchor="e")
        if isinstance(value, tk.Variable):
            tk.Label(block, textvariable=value, bg=self.BG, fg=self.TEXT, font=("Consolas", 10, "bold")).pack(anchor="e")
        else:
            tk.Label(block, text=value, bg=self.BG, fg=self.TEXT, font=("Consolas", 10, "bold")).pack(anchor="e")

    def _build_controls(self, parent: ttk.Frame) -> None:
        controls = tk.Frame(parent, bg=self.SURFACE, highlightbackground=self.BORDER, highlightthickness=1)
        controls.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        controls.columnconfigure(0, weight=1)
        tk.Label(controls, text="02 / 真实动作", bg=self.SURFACE, fg=self.MUTED, font=("Consolas", 9, "bold")).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 2))
        tk.Label(controls, text="先连接，再读取状态", bg=self.SURFACE, fg=self.TEXT, font=("Microsoft YaHei UI", 12, "bold")).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 10))
        self._connect_button = ttk.Button(controls, text=f"连接并读取状态 · {self._port}", style="Accent.TButton", command=self._connect)
        self._connect_button.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 7))
        self._status_button = ttk.Button(controls, text="读取状态 ?（不移动）", style="Motion.TButton", command=self._status, state="disabled")
        self._status_button.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 14))
        tk.Label(controls, text="XY · P0 安全范围", bg=self.SURFACE, fg=self.MUTED, font=("Microsoft YaHei UI", 9, "bold")).grid(row=4, column=0, sticky="w", padx=16, pady=(0, 5))
        for index, (label, action) in enumerate(BUTTON_ACTIONS.items()):
            button = ttk.Button(controls, text=label, style="Motion.TButton", command=lambda move=action: self._jog(*move), state="disabled")
            button.grid(row=5 + index, column=0, sticky="ew", padx=14, pady=3)
            self._motion_buttons.append(button)
        tk.Label(controls, text="串口：115200 · 8-N-1 · 无流控\n动作：相对 jog · 每次 ≤ 5 mm\n坐标：P0 手动参考，不是编码器反馈", bg=self.SURFACE, fg=self.MUTED, justify="left", anchor="w", font=("Consolas", 8)).grid(row=12, column=0, sticky="w", padx=16, pady=(17, 14))

    def _build_stream(self, parent: ttk.Frame) -> None:
        stream = tk.Frame(parent, bg=self.SURFACE, highlightbackground=self.BORDER, highlightthickness=1)
        stream.grid(row=0, column=1, sticky="nsew")
        stream.columnconfigure(0, weight=1)
        stream.rowconfigure(2, weight=1)
        tk.Label(stream, text="03 / 原始协议流", bg=self.SURFACE, fg=self.MUTED, font=("Consolas", 9, "bold")).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 2))
        tk.Label(stream, text="真实字节的可读转写", bg=self.SURFACE, fg=self.TEXT, font=("Microsoft YaHei UI", 12, "bold")).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 9))
        log_frame = tk.Frame(stream, bg="#07131f")
        log_frame.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 8))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self._log = scrolledtext.ScrolledText(log_frame, height=20, wrap="none", state="disabled", bg="#07131f", fg=self.TEXT, insertbackground=self.TEXT, relief="flat", bd=0, padx=12, pady=10, font=("Consolas", 10))
        self._log.grid(row=0, column=0, sticky="nsew")
        self._log.tag_configure("CALL", foreground=self.BLUE)
        self._log.tag_configure("TX", foreground=self.AMBER)
        self._log.tag_configure("RX", foreground=self.GREEN)
        self._log.tag_configure("ERROR", foreground=self.RED)
        self._log.tag_configure("NOTE", foreground=self.MUTED)
        tk.Label(stream, textvariable=self._last_event, bg=self.SURFACE, fg=self.MUTED, anchor="w", font=("Consolas", 8)).grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 12))

    def _draw_chain(self, active: str | None = None) -> None:
        if not hasattr(self, "_chain"):
            return
        canvas = self._chain
        canvas.delete("all")
        width = max(canvas.winfo_width(), 700)
        gap = width / len(CHAIN_STAGES)
        for index, stage in enumerate(CHAIN_STAGES):
            x = gap * index + gap / 2
            if index < len(CHAIN_STAGES) - 1:
                canvas.create_line(x + 72, 62, x + gap - 72, 62, fill=self.BORDER, width=2)
            is_active = stage.key == active
            fill = "#155640" if is_active else self.SURFACE_2
            outline = self.GREEN if is_active else self.BORDER
            canvas.create_oval(x - 31, 31, x + 31, 93, fill=fill, outline=outline, width=2)
            canvas.create_text(x, 62, text=str(index + 1).zfill(2), fill=self.TEXT if is_active else self.MUTED, font=("Consolas", 13, "bold"))
            canvas.create_text(x, 108, text=stage.title, fill=self.TEXT if is_active else self.MUTED, font=("Microsoft YaHei UI", 9, "bold"))
            canvas.create_text(x, 126, text=stage.detail, fill=self.MUTED, font=("Microsoft YaHei UI", 8))

    def _connect(self) -> None:
        if self._worker is not None and self._worker.is_running:
            return
        self._state.set(f"正在连接 {self._port} · 连接本身不发送运动命令")
        self._connect_button.configure(state="disabled")
        self._worker = GrblWorker(self._port, self._events)
        self._worker.start()

    def _status(self) -> None:
        if self._worker is not None:
            self._worker.request_status()

    def _jog(self, axis: str, distance_mm: float, feed_mm_min: float) -> None:
        if self._worker is not None:
            self._state.set(f"请求真实运动 · {axis}{distance_mm:g} mm · F{feed_mm_min:g}")
            self._worker.request_jog(axis, distance_mm, feed_mm_min)

    def _drain_events(self) -> None:
        while True:
            try:
                kind, payload = self._events.get_nowait()
            except queue.Empty:
                break
            if kind == "trace":
                event = payload
                label, text = format_trace_event(event)
                tag = {"PYTHON": "CALL", "TX → GRBL": "TX", "GRBL → RX": "RX"}.get(label, "CALL")
                self._append_log(f"[{label:<10}] {text}", tag)
                self._draw_chain(event_stage(event))
                self._explanation.set(describe_trace_event(event))
                self._last_event.set(f"最新事件 · {label} · {text}")
            elif kind == "connected":
                self._connection.set("ONLINE")
                self._state.set(f"已连接 {payload} · 首次状态查询已执行 · 等待真实动作")
                self._status_button.configure(state="normal")
                for button in self._motion_buttons:
                    button.configure(state="normal")
            elif kind == "status":
                status = payload
                self._grbl_state.set(status.strip("<>").split("|", 1)[0])
                try:
                    position = parse_mpos(status)
                    self._position.set(f"MPos {position.x:.1f}, {position.y:.1f}, {position.z:.1f}")
                except ValueError:
                    self._position.set("MPos  —")
                self._state.set(f"GRBL 状态 · {status}")
            elif kind == "motion_done":
                command = payload
                self._state.set(f"真实运动完成 · {command.axis}{command.distance_mm:g} mm · 请同时观察机械运动")
            elif kind == "error":
                self._connection.set("ERROR")
                self._state.set(f"错误 · {payload}")
                self._append_log(f"[ERROR     ] {payload}", "ERROR")
                self._explanation.set("控制器拒绝或未完成本次动作；请先检查电源、端口和机械余量。")
            elif kind == "disconnected":
                self._connection.set("OFFLINE")
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
