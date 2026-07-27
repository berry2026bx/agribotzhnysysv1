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
from .workspace import Position, parse_mpos, validate_xy_target


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


def format_stream_row(sequence: int, event: TraceEvent) -> tuple[str, str, str]:
    """Return one compact live-log row; long teaching text belongs in the detail pane."""

    label, text = format_trace_event(event)
    return f"#{sequence:02d}  {event.kind}  {label}", text, describe_trace_event(event)


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
class TeachingExplanation:
    """One live event explained for a teacher and for a developer."""

    stage: str
    heading: str
    plain: str
    technical: str
    code: str


@dataclass(frozen=True)
class StatusExplanation:
    state: str
    position: Position
    plain: str
    technical: str


@dataclass(frozen=True)
class CoordinateStatus:
    """One coordinate record derived from an observed GRBL status frame."""

    state: str
    position: Position
    change: str


@dataclass(frozen=True)
class StatusField:
    name: str
    value: str
    meaning: str


@dataclass(frozen=True)
class ProtocolGuideEntry:
    term: str
    title: str
    summary: str
    detail: str
    example: str


PROTOCOL_GUIDE = (
    ProtocolGuideEntry(
        "串口",
        "什么是串口？",
        "电脑与控制板之间的一条有顺序的数据通道。",
        "这里使用 USB 转 CH340 芯片，把电脑里的字节送到 Arduino/GRBL，再把返回字节送回来。",
        "COMx · 115200 baud · 8-N-1",
    ),
    ProtocolGuideEntry(
        "115200",
        "波特率",
        "每秒传输的符号速度。",
        "双方必须使用同一个速度；本机设置为 115200。速度不一致时，收到的字符会变成乱码或超时。",
        "baudrate=115200",
    ),
    ProtocolGuideEntry(
        "8-N-1",
        "一帧串口的基本格式",
        "8 个数据位、无校验、1 个停止位。",
        "它规定一个字节怎样排成电信号；它不是 GRBL 指令内容，而是串口线路的约定。",
        "8 data bits · No parity · 1 stop bit",
    ),
    ProtocolGuideEntry(
        "GRBL",
        "控制板里的运动固件",
        "运行在 Arduino 上、负责把指令变成步进脉冲的软件。",
        "Python 不直接控制 A4988 的每一个脉冲；Python 把指令交给 GRBL，GRBL 再管理运动状态和坐标。",
        "Arduino UNO + GRBL 1.1f",
    ),
    ProtocolGuideEntry(
        "TX",
        "Transmit：电脑发出的数据",
        "TX 行表示 Python 实际写入当前串口的内容。",
        "它是证据链中的‘发送’方向；界面中的 TX 不是预演，而是控制器写串口时记录的真实载荷。",
        'TX  $J=G91 G21 X5 F100\\n',
    ),
    ProtocolGuideEntry(
        "RX",
        "Receive：控制板返回的数据",
        "RX 行表示 Python 从 GRBL 实际读到的内容。",
        "RX 可能是 ok、状态帧、error 或 ALARM；不同返回值代表不同阶段，不能只看一个 ok。",
        "RX  <Idle|MPos:12.500,-3.000,4.000>",
    ),
    ProtocolGuideEntry(
        "$J=",
        "GRBL Jog 指令",
        "请求 GRBL 做一次受限的相对移动。",
        "本系统只允许这一类受限 Jog，不发送任意 G-code。换行符表示这条文本指令结束。",
        "$J=G91 G21 X5 F100\\n",
    ),
    ProtocolGuideEntry(
        "G91 / G21 / F",
        "一条 Jog 指令的组成",
        "相对坐标、毫米单位、移动速度。",
        "G91 表示‘从当前位置移动这么多’；G21 表示单位是毫米；X/Y/Z 后面的数字是增量；F 是速度，单位 mm/min。",
        "G91 · G21 · X5 · F100",
    ),
    ProtocolGuideEntry(
        "ok",
        "协议确认，不是完成证明",
        "GRBL 表示它已经接收并接受了这一行。",
        "电机可能仍在运动；控制器必须继续发送 ? 并等待最终 Idle。把 ok 当作完成是常见误读。",
        "RX  ok",
    ),
    ProtocolGuideEntry(
        "<Idle|MPos:…>",
        "状态帧",
        "GRBL 对当前运动状态的一次结构化报告。",
        "尖括号是帧边界；第一个字段是状态；MPos 后的三个数依次是 X/Y/Z。其它字段可能包含速度或缓冲区信息。",
        "<Idle|MPos:12.500,-3.000,4.000|FS:0,0>",
    ),
    ProtocolGuideEntry(
        "MPos",
        "机器坐标字段",
        "GRBL 固件内部记录的 X/Y/Z 位置。",
        "它不是编码器测量值，也不自动知道手工标记的 P0；重新连接或人为移动后，必须重新确认物理参考。",
        "MPos:X,Y,Z",
    ),
    ProtocolGuideEntry(
        "P0",
        "实验中的手动参考点",
        "用标记物理位置建立的起始参考。",
        "P0 不是 GRBL 的硬件回零，也不是编码器原点；本系统用它约束已测量的 XY 工作范围。",
        "X[-190,190] · Y[-90,140] mm",
    ),
)


def protocol_guide() -> tuple[ProtocolGuideEntry, ...]:
    """Return the stable glossary used by the optional protocol dictionary window."""

    return PROTOCOL_GUIDE


def explain_trace_event(event: TraceEvent) -> TeachingExplanation:
    """Turn an observed event into plain-language and protocol-level teaching text."""

    stage = event_stage(event)
    text = event.text.strip()
    if event.kind == "CALL":
        if "jog" in text.lower():
            return TeachingExplanation(
                stage,
                "Python 发起一次相对移动",
                "按钮已经进入 Python；Python 正在调用一个保持连接的控制器。",
                "控制器会先读取 Idle 状态，再写入受限的 GRBL Jog 指令。",
                "controller.jog(JogCommand(...))",
            )
        if "status" in text.lower():
            return TeachingExplanation(
                stage,
                "Python 请求读取状态",
                "这一步只问机器现在怎么样，不要求它移动。",
                "状态请求使用 GRBL 的实时查询字符 ?，随后等待状态帧。",
                "controller.status()",
            )
        return TeachingExplanation(stage, "Python 控制器动作", "Python 正在管理串口连接。", text, text)
    if event.kind == "TX":
        if text == "?":
            return TeachingExplanation(
                stage,
                "Python 询问实时状态",
                "问 GRBL：你现在是空闲、运动中，还是报警？这一步不会移动机器。",
                "? 是 GRBL 实时状态查询字节，不是普通 G-code；它不需要换行。",
                'serial.write(b"?")',
            )
        code = f'serial.write(b"{text}\\n")'
        return TeachingExplanation(
            stage,
            "Python 发出运动指令",
            "这句话告诉 GRBL：做一次相对移动，沿哪个轴、移动多少毫米、用多快的速度移动。",
            "G91=相对坐标；G21=毫米；轴值是本次增量；F=进给速度；末尾换行表示一条指令结束。",
            code,
        )
    if event.kind == "RX":
        if text == "ok":
            return TeachingExplanation(
                stage,
                "GRBL 已收到指令",
                "GRBL 说‘我收到了’，但电机可能还在运动，所以还不能宣布完成。",
                "ok 是协议层确认（acknowledgement），不是位置反馈，也不是动作完成信号。",
                "response == b\"ok\\r\\n\"",
            )
        if text.startswith("<"):
            state = text.strip("<>").split("|", 1)[0]
            if state == "Idle":
                return TeachingExplanation(
                    stage,
                    "GRBL 报告动作完成",
                    "GRBL 现在回到 Idle，说明这次控制循环已经结束；屏幕上的坐标是固件报告的位置。",
                    "状态帧以 < 开始，以 > 结束；Idle 是状态字段，MPos 是 GRBL 内部的位置记录。",
                    f"status = {text!r}",
                )
            return TeachingExplanation(
                stage,
                f"GRBL 状态：{state}",
                "机器还没有回到空闲状态，控制器会继续询问，直到收到 Idle。",
                "状态帧的第一个字段是状态机状态；非 Idle 不能当作动作完成。",
                f"status = {text!r}",
            )
        if text.startswith("error:") or text.startswith("ALARM:"):
            return TeachingExplanation(stage, "GRBL 拒绝或报警", "机器没有接受这一步，请先处理错误，再继续移动。", "GRBL 返回错误帧；控制器会停止本次动作。", f"response = {text!r}")
    return TeachingExplanation(stage, "收到一条串口事件", "屏幕保留了原始内容，但暂时没有更高层解释。", "未分类 TraceEvent。", repr(text))


def explain_status(status_raw: str) -> StatusExplanation:
    """Explain a real GRBL status frame and expose its parsed coordinates."""

    state = status_raw.strip("<>").split("|", 1)[0]
    position = parse_mpos(status_raw)
    plain = f"GRBL 当前是 {state}。它报告 X={position.x:g} mm、Y={position.y:g} mm、Z={position.z:g} mm。"
    technical = "MPos 是 GRBL 固件内部的位置记录；它不是编码器测量值，也不会替代重新对齐 P0。"
    return StatusExplanation(state, position, plain, technical)


def record_coordinate_status(status_raw: str, previous: Position | None) -> CoordinateStatus:
    """Create a display record from a real MPos frame, never from a button intent."""

    explanation = explain_status(status_raw)
    position = explanation.position
    if previous is None:
        change = "首次状态帧：建立 GRBL 当前 MPos 记录。"
    else:
        change = (
            "相对上一帧："
            f"X {position.x - previous.x:+.3f} mm；"
            f"Y {position.y - previous.y:+.3f} mm；"
            f"Z {position.z - previous.z:+.3f} mm。"
        )
    return CoordinateStatus(explanation.state, position, change)


def parse_status_fields(status_raw: str) -> tuple[StatusField, ...]:
    """Split a GRBL status frame into named, human-readable fields."""

    body = status_raw.strip()
    if not (body.startswith("<") and body.endswith(">")):
        raise ValueError(f"invalid GRBL status frame: {status_raw!r}")
    fields = body[1:-1].split("|")
    if not fields or not fields[0]:
        raise ValueError(f"status frame has no state: {status_raw!r}")
    result: list[StatusField] = [
        StatusField("状态", fields[0], _status_meaning(fields[0])),
    ]
    for field in fields[1:]:
        name, separator, value = field.partition(":")
        if not separator:
            result.append(StatusField(name, "", "GRBL 返回了一个没有冒号的扩展字段。"))
            continue
        if name in {"MPos", "WPos"}:
            values = value.split(",")
            if len(values) < 3:
                raise ValueError(f"invalid {name} field: {field!r}")
            result.append(StatusField(name, f"X={values[0]} mm，Y={values[1]} mm，Z={values[2]} mm", "三个数依次对应 X、Y、Z 坐标。"))
        elif name == "FS":
            values = value.split(",")
            if len(values) < 2:
                raise ValueError(f"invalid FS field: {field!r}")
            result.append(StatusField(name, f"进给 {values[0]} mm/min；主轴 {values[1]} RPM", "第一个数是当前进给速度，第二个数是主轴转速；本写字机主轴转速为 0。"))
        elif name == "F":
            result.append(StatusField(name, f"进给 {value} mm/min", "当前进给速度；没有主轴速度字段。"))
        elif name == "Pn":
            result.append(StatusField(name, value or "无触发输入", _pin_meaning(value)))
        else:
            result.append(StatusField(name, value, "GRBL 状态报告中的扩展字段；其精确定义取决于字段名称。"))
    return tuple(result)


def format_frame_fields(event: TraceEvent) -> str:
    """Translate a real event into direction, full names, values, and evidence limits."""

    if event.kind == "RX" and event.text.strip().startswith("<"):
        labels = {
            "状态": "State / 机器状态",
            "MPos": "MPos / Machine Position（机器坐标）",
            "WPos": "WPos / Work Position（工作坐标）",
            "FS": "FS / Feed rate and Spindle speed（进给速度 / 主轴转速）",
            "F": "F / Feed rate（进给速度）",
            "Pn": "Pn / Pin State（输入引脚状态）",
        }
        lines = [
            "RX / Receive（接收）",
            "方向：GRBL → 电脑。电脑正在读取控制板主动报告的状态。",
            "< >：这一对尖括号包住一整帧状态报告。",
        ]
        for field in parse_status_fields(event.text):
            label = labels.get(field.name, field.name)
            lines.append(f"{label} = {field.value}\n作用：{field.meaning}")
            if field.name == "状态":
                decision = "可以作为 GRBL 报告本次控制周期结束的依据；仍需现场观察机构。" if field.value == "Idle" else "不能作为完成依据：控制器尚未报告 Idle。"
                lines.append(f"判断：{decision}")
            elif field.name in {"MPos", "WPos"}:
                lines.append("证据边界：这是 GRBL 内部位置记录，不是编码器实测；断电、手推或丢步后必须重新对齐 P0。")
            elif field.name == "Pn":
                lines.append("判断：输入电平被检测到，不等于机械端已经真实接触目标。")
        return "\n\n".join(lines)
    if event.kind == "TX" and event.text.strip() == "?":
        return "TX / Transmit（发送）\n方向：电脑 → GRBL。\n本帧：?\n含义：实时状态查询，不是运动指令，不会让机器移动，也不需要换行。"
    if event.kind == "TX" and event.text.strip().startswith("$J="):
        command = event.text.strip()
        return f"TX / Transmit（发送）\n方向：电脑 → GRBL。\n本帧：{command}\n$J= / Jog request：请求一次受限点动；整行是 ASCII 文本，换行符表示指令结束。"
    if event.kind == "RX" and event.text.strip() == "ok":
        return "RX / Receive（接收）\n方向：GRBL → 电脑。\n本帧：ok\nok / acknowledgement：GRBL 已接收并接受指令。\n判断：不能作为完成依据；仍要继续查询，直到收到 Idle。"
    if event.kind == "CALL":
        return f"CALL / Python function call（函数调用）\n位置：发生在电脑程序内部，尚未写入串口。\n本帧：{event.text}"
    return f"{event.kind}：{event.text}"


def _status_meaning(state: str) -> str:
    return {
        "Idle": "控制器空闲，可以接受下一次受限动作。",
        "Jog": "控制器正在 Jog，机器处于运动中，不能把这一行当作完成。",
        "Alarm": "控制器处于报警状态，需要先排除报警原因。",
        "Hold": "运动被暂停，尚未完成。",
    }.get(state, f"GRBL 当前状态为 {state}。")


def _pin_meaning(value: str) -> str:
    if not value:
        return "没有检测到触发输入。"
    meanings = []
    labels = {
        "X": "X 限位",
        "Y": "Y 限位",
        "Z": "Z 限位",
        "P": "Probe 探针输入",
        "D": "门控输入",
        "H": "暂停输入",
        "R": "软复位输入",
        "S": "循环启动输入",
    }
    for pin in value:
        meanings.append(labels.get(pin, f"未知输入 {pin}"))
    return "GRBL 检测到触发：" + "、".join(meanings) + "。这表示输入电平被检测为触发，不自动证明机械端已经接触目标。"


@dataclass(frozen=True)
class ChainStage:
    key: str
    title: str
    detail: str


CHAIN_STAGES = (
    ChainStage("python", "Python 调用", "持久控制器接到动作请求"),
    ChainStage("command", "TX 运动指令", "ASCII 写入当前串口"),
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
    """A calm three-page desktop classroom for real GRBL events."""

    BG = "#f6f8f9"
    SURFACE = "#ffffff"
    SURFACE_ALT = "#f1f4f5"
    BORDER = "#d7dfe3"
    TEXT = "#1f2933"
    MUTED = "#62717b"
    NAVY = "#1d4e89"
    TEAL = "#0b6e69"
    BLUE = "#2563eb"
    PURPLE = "#6d28d9"
    GREEN = "#1f7a45"
    AMBER = "#b54708"
    RED = "#b42318"

    def __init__(self, root: tk.Tk, port: str) -> None:
        self._root = root
        self._port = port
        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._worker: GrblWorker | None = None
        self._motion_buttons: list[ttk.Button] = []
        self._history: list[tuple[int, TraceEvent, TeachingExplanation]] = []
        self._position_history: list[CoordinateStatus] = []
        self._sequence = 0
        self._current_position = Position(0.0, 0.0, 0.0)
        self._active_chain_stage: str | None = None
        self._root.title("DayuWriter · 现场控制与通信说明")
        self._root.geometry("1560x1040")
        self._root.minsize(1280, 900)
        self._root.configure(bg=self.BG)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._configure_style()
        self._state = tk.StringVar(value=f"尚未连接：点击‘连接并读取状态’后才会打开 {self._port}")
        self._connection = tk.StringVar(value="未连接")
        self._grbl_state = tk.StringVar(value="—")
        self._position = tk.StringVar(value="X —   Y —   Z — mm")
        self._event_counter = tk.StringVar(value="0 条真实事件")
        self._chain_summary = tk.StringVar(value="尚未连接。连接后，此处只高亮实际发生的通信阶段。")
        self._detail_stage = tk.StringVar(value="等待事件")
        self._detail_heading = tk.StringVar(value="等待第一条真实通信")
        self._detail_plain = tk.StringVar(value="先点击“连接并读取状态”。界面只记录真实 Python 调用和真实串口收发，不生成模拟通信。")
        self._detail_technical = tk.StringVar(value="CALL = Python function call，发生在程序内部；TX = Transmit，电脑发送给 GRBL；RX = Receive，电脑从 GRBL 接收。")
        self._detail_fields = tk.StringVar(value="等待真实帧。收到后会按：英文全称 → 当前值 → 中文作用 → 能否作为完成依据，逐项解释。")
        self._detail_code = tk.StringVar(value="等待真实 Python / 串口调用")
        self._detail_raw = tk.StringVar(value="原始帧：—")
        self._coord_plain = tk.StringVar(value="等待 GRBL 返回 MPos")
        self._coord_technical = tk.StringVar(value="MPos 是 GRBL 内部位置记录，不是编码器反馈。")
        self._build_ui()
        self._root.after(100, self._drain_events)

    def _configure_style(self) -> None:
        style = ttk.Style(self._root)
        style.theme_use("clam")
        style.configure("Action.TButton", background=self.NAVY, foreground="#ffffff", padding=(12, 10), font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Action.TButton", background=[("active", "#236b9e"), ("disabled", "#a9b9c4")])
        style.configure("Move.TButton", background=self.SURFACE_ALT, foreground=self.TEXT, padding=(8, 8), font=("Microsoft YaHei UI", 10))
        style.map("Move.TButton", background=[("active", "#d9e9f3"), ("disabled", "#f0f2f4")])
        style.configure("TNotebook", background=self.BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#e6edf2", foreground=self.MUTED, padding=(18, 9), font=("Microsoft YaHei UI", 10, "bold"))
        style.map("TNotebook.Tab", background=[("selected", self.SURFACE)], foreground=[("selected", self.NAVY)])

    def _panel(self, parent: tk.Widget, row: int, column: int, *, padx: tuple[int, int] = (0, 0)) -> tk.Frame:
        frame = tk.Frame(parent, bg=self.SURFACE, highlightbackground=self.BORDER, highlightthickness=1)
        frame.grid(row=row, column=column, sticky="nsew", padx=padx)
        return frame

    def _label(self, parent: tk.Widget, text: str, *, size: int = 10, color: str | None = None, bold: bool = False, **kwargs: object) -> tk.Label:
        return tk.Label(parent, text=text, bg=self.SURFACE, fg=color or self.TEXT, font=("Microsoft YaHei UI", size, "bold" if bold else "normal"), **kwargs)

    def _build_ui(self) -> None:
        self._root.columnconfigure(0, weight=1)
        self._root.rowconfigure(0, weight=1)
        outer = tk.Frame(self._root, bg=self.BG, padx=24, pady=20)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)
        self._build_header(outer)
        self._tabs = ttk.Notebook(outer)
        self._tabs.grid(row=1, column=0, sticky="nsew")
        live = tk.Frame(self._tabs, bg=self.BG)
        communication = tk.Frame(self._tabs, bg=self.BG)
        coordinates = tk.Frame(self._tabs, bg=self.BG)
        self._tabs.add(live, text="现场控制")
        self._tabs.add(communication, text="通信入门")
        self._tabs.add(coordinates, text="坐标入门")
        self._build_live_page(live)
        self._build_communication_page(communication)
        self._build_coordinate_page(coordinates)
        self._render_flow()
        tk.Label(outer, textvariable=self._state, bg=self.BG, fg=self.MUTED, anchor="w", font=("Microsoft YaHei UI", 9)).grid(row=2, column=0, sticky="ew", pady=(10, 0))

    def _build_header(self, parent: tk.Frame) -> None:
        header = tk.Frame(parent, bg=self.BG)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        header.columnconfigure(1, weight=1)
        tk.Label(header, text="DAYUWRITER  /  LIVE CONTROL", bg=self.BG, fg=self.TEAL, font=("Consolas", 10, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(header, text="现场控制与通信说明", bg=self.BG, fg=self.TEXT, font=("Microsoft YaHei UI", 24, "bold")).grid(row=1, column=0, sticky="w", pady=(2, 0))
        tk.Label(header, text="实时数据、协议解释、坐标信息分层展示，互不挤占。", bg=self.BG, fg=self.MUTED, font=("Microsoft YaHei UI", 11)).grid(row=2, column=0, sticky="w", pady=(3, 0))
        metrics = tk.Frame(header, bg=self.BG)
        metrics.grid(row=0, column=1, rowspan=3, sticky="e")
        self._metric(metrics, "串口", self._port, 0, self.NAVY)
        self._metric(metrics, "连接", self._connection, 1, self.TEAL)
        self._metric(metrics, "GRBL", self._grbl_state, 2, self.AMBER)
        self._metric(metrics, "坐标", self._position, 3, self.BLUE)
        tk.Label(metrics, textvariable=self._event_counter, bg=self.BG, fg=self.MUTED, font=("Consolas", 9)).grid(row=1, column=0, columnspan=4, sticky="e", pady=(7, 0))

    def _metric(self, parent: tk.Widget, title: str, value: tk.Variable | str, column: int, color: str) -> None:
        block = tk.Frame(parent, bg=self.BG)
        block.grid(row=0, column=column, padx=(24 if column else 0, 0), sticky="e")
        tk.Label(block, text=title, bg=self.BG, fg=self.MUTED, font=("Microsoft YaHei UI", 8, "bold")).pack(anchor="e")
        kwargs = {"textvariable": value} if isinstance(value, tk.Variable) else {"text": value}
        tk.Label(block, bg=self.BG, fg=color, font=("Consolas", 11, "bold"), **kwargs).pack(anchor="e")

    def _build_live_page(self, parent: tk.Frame) -> None:
        parent.columnconfigure(0, weight=0, minsize=285)
        parent.columnconfigure(1, weight=1, minsize=640)
        parent.columnconfigure(2, weight=0, minsize=410)
        parent.rowconfigure(0, weight=0)
        parent.rowconfigure(1, weight=1)
        self._build_causal_chain(parent)
        self._build_controls(parent, 1)
        self._build_stream(parent, 1)
        self._build_current_detail(parent, 1)

    def _build_causal_chain(self, parent: tk.Frame) -> None:
        band = tk.Frame(parent, bg=self.SURFACE, highlightbackground=self.BORDER, highlightthickness=1)
        band.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 14))
        band.columnconfigure(0, weight=1)
        tk.Label(band, text="通信因果链", bg=self.SURFACE, fg=self.NAVY, font=("Microsoft YaHei UI", 12, "bold"), anchor="w").grid(row=0, column=0, sticky="w", padx=18, pady=(12, 0))
        tk.Label(band, text="CALL = Python function call（程序内部调用）   ·   TX = Transmit（电脑发送）   ·   RX = Receive（电脑接收）", bg=self.SURFACE, fg=self.MUTED, font=("Microsoft YaHei UI", 9), anchor="w").grid(row=1, column=0, sticky="w", padx=18, pady=(0, 4))
        self._chain_canvas = tk.Canvas(band, height=72, bg=self.SURFACE, bd=0, highlightthickness=0)
        self._chain_canvas.grid(row=2, column=0, sticky="ew", padx=12)
        self._chain_canvas.bind("<Configure>", lambda _event: self._draw_causal_chain())
        tk.Label(band, textvariable=self._chain_summary, bg=self.SURFACE, fg=self.TEXT, font=("Microsoft YaHei UI", 9), anchor="w", justify="left", wraplength=1400).grid(row=3, column=0, sticky="ew", padx=18, pady=(1, 10))
        self._draw_causal_chain()

    def _build_controls(self, parent: tk.Frame, row: int) -> None:
        controls = self._panel(parent, row, 0, padx=(0, 14))
        controls.columnconfigure(0, weight=1)
        self._label(controls, "动作控制", size=10, color=self.TEAL, bold=True).grid(row=0, column=0, sticky="w", padx=16, pady=(18, 2))
        self._label(controls, "先查状态，再移动", size=15, bold=True).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 5))
        self._label(controls, "按钮调用真实 Python 控制器；未连接时所有动作保持禁用。", size=9, color=self.MUTED, justify="left", wraplength=245).grid(row=2, column=0, sticky="w", padx=16, pady=(0, 14))
        self._connect_button = ttk.Button(controls, text=f"连接并读取状态 · {self._port}", style="Action.TButton", command=self._connect)
        self._connect_button.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 7))
        self._status_button = ttk.Button(controls, text="只读查询 ?（不移动）", style="Move.TButton", command=self._status, state="disabled")
        self._status_button.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 18))
        self._axis_group(controls, 5, "X 轴 · 左右", ("X 左 −5 mm", "X 右 +5 mm"), (BUTTON_ACTIONS["X 向左 -5 mm"], BUTTON_ACTIONS["X 向右 +5 mm"]))
        self._axis_group(controls, 7, "Y 轴 · 前后", ("Y 后 −5 mm", "Y 前 +5 mm"), (BUTTON_ACTIONS["Y 向后 -5 mm"], BUTTON_ACTIONS["Y 向前 +5 mm"]))
        self._axis_group(controls, 9, "Z 轴 · 上下", ("Z 上 −1 mm", "Z 下 +1 mm"), (BUTTON_ACTIONS["Z 向上 -1 mm"], BUTTON_ACTIONS["Z 向下 +1 mm"]))
        self._label(controls, "连接参数", size=9, color=self.NAVY, bold=True).grid(row=11, column=0, sticky="w", padx=16, pady=(18, 3))
        self._label(controls, "115200 baud · 8-N-1 · 无流控\nP0 是手动参考点，不是编码器原点。", size=9, color=self.MUTED, justify="left").grid(row=12, column=0, sticky="w", padx=16, pady=(0, 18))
        glossary = tk.Frame(controls, bg=self.SURFACE_ALT, highlightbackground=self.BORDER, highlightthickness=1)
        glossary.grid(row=13, column=0, sticky="ew", padx=14, pady=(0, 16))
        tk.Label(glossary, text="术语速读", bg=self.SURFACE_ALT, fg=self.NAVY, font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(anchor="w", padx=12, pady=(9, 4))
        tk.Label(glossary, text="CALL：Python 内部函数调用，尚未上串口\nTX / Transmit：电脑 → GRBL\nRX / Receive：GRBL → 电脑\nok：已接收，不等于完成\nIdle：GRBL 报告本轮控制结束", bg=self.SURFACE_ALT, fg=self.TEXT, font=("Microsoft YaHei UI", 9), justify="left", anchor="w").pack(anchor="w", padx=12, pady=(0, 10))

    def _axis_group(self, parent: tk.Frame, row: int, title: str, labels: tuple[str, str], actions: tuple[tuple[str, float, float], tuple[str, float, float]]) -> None:
        tk.Label(parent, text=title, bg=self.SURFACE, fg=self.MUTED, font=("Microsoft YaHei UI", 9, "bold")).grid(row=row, column=0, sticky="w", padx=16, pady=(4, 4))
        holder = tk.Frame(parent, bg=self.SURFACE)
        holder.grid(row=row + 1, column=0, sticky="ew", padx=14)
        holder.columnconfigure(0, weight=1)
        holder.columnconfigure(1, weight=1)
        for column, (label, action) in enumerate(zip(labels, actions)):
            button = ttk.Button(holder, text=label, style="Move.TButton", command=lambda move=action: self._jog(*move), state="disabled")
            button.grid(row=0, column=column, sticky="ew", padx=(0, 4) if column == 0 else (4, 0))
            self._motion_buttons.append(button)

    def _build_stream(self, parent: tk.Frame, row: int) -> None:
        panel = self._panel(parent, row, 1, padx=(0, 14))
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(2, weight=3)
        panel.rowconfigure(4, weight=2)
        self._label(panel, "真实通信证据", size=10, color=self.BLUE, bold=True).grid(row=0, column=0, sticky="w", padx=16, pady=(18, 2))
        self._label(panel, "谁发出、发给谁、原文是什么", size=15, bold=True).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 10))
        self._flow = scrolledtext.ScrolledText(panel, height=14, wrap="word", state="disabled", bg="#f8fbfd", fg=self.TEXT, relief="flat", bd=0, padx=14, pady=14, font=("Consolas", 10), spacing1=2, spacing3=5)
        self._flow.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 14))
        self._flow.tag_configure("call", foreground=self.BLUE, font=("Consolas", 10, "bold"))
        self._flow.tag_configure("tx", foreground=self.AMBER, font=("Consolas", 10, "bold"))
        self._flow.tag_configure("rx", foreground=self.GREEN, font=("Consolas", 10, "bold"))
        self._flow.tag_configure("payload", foreground=self.TEXT)
        self._flow.tag_configure("summary", foreground=self.MUTED, font=("Microsoft YaHei UI", 9))
        self._label(panel, "真实 MPos 坐标历程", size=10, color=self.TEAL, bold=True).grid(row=3, column=0, sticky="w", padx=16, pady=(2, 4))
        history = tk.Frame(panel, bg=self.SURFACE)
        history.grid(row=4, column=0, sticky="nsew", padx=14, pady=(0, 14))
        history.columnconfigure(0, weight=3)
        history.columnconfigure(1, weight=2)
        history.rowconfigure(0, weight=1)
        self._trajectory_canvas = tk.Canvas(history, height=168, bg="#ffffff", bd=0, highlightbackground=self.BORDER, highlightthickness=1)
        self._trajectory_canvas.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self._trajectory_canvas.bind("<Configure>", lambda _event: self._draw_coordinate_history())
        self._position_history_text = scrolledtext.ScrolledText(history, height=9, wrap="word", state="disabled", bg="#f8fbfd", fg=self.TEXT, relief="flat", bd=0, padx=12, pady=10, font=("Consolas", 9), spacing1=2, spacing3=3)
        self._position_history_text.grid(row=0, column=1, sticky="nsew")
        self._position_history_text.tag_configure("sample", foreground=self.TEAL, font=("Consolas", 9, "bold"))
        self._position_history_text.tag_configure("change", foreground=self.TEXT)
        self._position_history_text.tag_configure("notice", foreground=self.MUTED, font=("Microsoft YaHei UI", 8))
        self._render_coordinate_history()

    def _build_current_detail(self, parent: tk.Frame, row: int) -> None:
        panel = self._panel(parent, row, 2)
        panel.columnconfigure(0, weight=1)
        self._label(panel, "当前事件", size=10, color=self.PURPLE, bold=True).grid(row=0, column=0, sticky="w", padx=16, pady=(18, 2))
        tk.Label(panel, textvariable=self._detail_stage, bg=self.SURFACE, fg=self.PURPLE, font=("Consolas", 10, "bold"), anchor="w").grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 5))
        tk.Label(panel, textvariable=self._detail_heading, bg=self.SURFACE, fg=self.TEXT, font=("Microsoft YaHei UI", 16, "bold"), anchor="w", justify="left", wraplength=370).grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        self._detail_block(panel, 3, "这一步在做什么", self._detail_plain, self.NAVY, 11)
        self._detail_block(panel, 5, "通信与代码含义", self._detail_technical, self.PURPLE, 9)
        self._detail_block(panel, 7, "字段翻译与证据判断", self._detail_fields, self.TEAL, 10)
        self._detail_block(panel, 9, "对应 Python 调用", self._detail_code, self.NAVY, 10, mono=True)
        self._detail_block(panel, 11, "原始帧（不改写）", self._detail_raw, self.AMBER, 9, mono=True)

    def _detail_block(self, parent: tk.Frame, row: int, title: str, variable: tk.Variable, color: str, size: int, *, mono: bool = False) -> None:
        block = tk.Frame(parent, bg=self.SURFACE_ALT, highlightbackground=self.BORDER, highlightthickness=1)
        block.grid(row=row, column=0, sticky="ew", padx=14, pady=(0, 8))
        tk.Label(block, text=title, bg=self.SURFACE_ALT, fg=color, font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(anchor="w", padx=12, pady=(8, 2))
        tk.Label(block, textvariable=variable, bg=self.SURFACE_ALT, fg=self.TEXT, font=(("Consolas" if mono else "Microsoft YaHei UI"), size), justify="left", anchor="w", wraplength=370).pack(anchor="w", padx=12, pady=(0, 10))

    def _build_communication_page(self, parent: tk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)
        tk.Label(parent, text="通信入门", bg=self.BG, fg=self.TEXT, font=("Microsoft YaHei UI", 20, "bold"), anchor="w").grid(row=0, column=0, sticky="w", padx=20, pady=(20, 4))
        tk.Label(parent, text="先理解数据方向，再看每一行协议内容。", bg=self.BG, fg=self.MUTED, font=("Microsoft YaHei UI", 11), anchor="w").grid(row=1, column=0, sticky="w", padx=20, pady=(0, 2))
        text = scrolledtext.ScrolledText(parent, wrap="word", bg="#ffffff", fg=self.TEXT, relief="flat", bd=0, padx=28, pady=22, font=("Microsoft YaHei UI", 11), spacing1=2, spacing3=5)
        text.grid(row=2, column=0, sticky="nsew", padx=20, pady=(16, 20))
        text.tag_configure("section", foreground=self.NAVY, font=("Microsoft YaHei UI", 15, "bold"), spacing1=13)
        text.tag_configure("term", foreground=self.TEAL, font=("Microsoft YaHei UI", 12, "bold"), spacing1=8)
        text.tag_configure("body", foreground=self.TEXT)
        text.tag_configure("code", foreground=self.AMBER, font=("Consolas", 10))
        text.insert("end", "先看完整链路\n", "section")
        text.insert("end", "按钮点击 → Python 函数 → pySerial 写入 TX → GRBL 解析 → 步进驱动器执行 → GRBL 通过 RX 返回状态。Python 负责提出请求和等待结果；GRBL 负责运动状态机、步进脉冲和坐标记录。\n\n", "body")
        text.insert("end", "一条运动动作通常会产生这些事件\n", "section")
        for line in (
            ("1  CALL", "Python 调用 controller.jog(...)。这是程序内部的函数调用，还没有把运动文本写到线路上。"),
            ("2  TX $J=...", "电脑把 ASCII 文本写到当前串口。G91 表示相对移动，G21 表示毫米，X/Y/Z 是移动量，F 是速度。"),
            ("3  RX ok", "GRBL 已经接受文本。它只是接收确认，不能证明机械运动已经结束。"),
            ("4  TX ?", "电脑发送一个实时查询字符，询问 GRBL 当前状态；它不是运动指令，不会让机器移动。"),
            ("5  RX <Jog|MPos:...>", "GRBL 报告自己还在 Jog 状态，并给出当前内部坐标。"),
            ("6  RX <Idle|MPos:...>", "GRBL 回到 Idle。控制器把它作为本次动作完成的条件。"),
        ):
            text.insert("end", f"{line[0]}\n", "term")
            text.insert("end", f"{line[1]}\n\n", "body")
        text.insert("end", "术语词典\n", "section")
        for entry in protocol_guide():
            text.insert("end", f"{entry.term} · {entry.title}\n", "term")
            text.insert("end", f"{entry.summary}\n{entry.detail}\n示例：{entry.example}\n\n", "body")
        text.configure(state="disabled")

    def _build_coordinate_page(self, parent: tk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(2, weight=1)
        tk.Label(parent, text="坐标入门", bg=self.BG, fg=self.TEXT, font=("Microsoft YaHei UI", 20, "bold"), anchor="w").grid(row=0, column=0, columnspan=2, sticky="w", padx=20, pady=(20, 4))
        tk.Label(parent, text="这张图只展示 GRBL 返回的 MPos，不把相机像素坐标混进来。", bg=self.BG, fg=self.MUTED, font=("Microsoft YaHei UI", 11), anchor="w").grid(row=1, column=0, columnspan=2, sticky="w", padx=20, pady=(0, 2))
        self._coord_canvas = tk.Canvas(parent, width=600, height=500, bg="#ffffff", bd=0, highlightbackground=self.BORDER, highlightthickness=1)
        self._coord_canvas.grid(row=2, column=0, sticky="nsew", padx=(20, 10), pady=(16, 20))
        self._coord_canvas.bind("<Configure>", lambda _event: self._draw_coordinates())
        info = tk.Frame(parent, bg=self.SURFACE, highlightbackground=self.BORDER, highlightthickness=1)
        info.grid(row=2, column=1, sticky="nsew", padx=(10, 20), pady=(16, 20))
        self._label(info, "坐标怎样读", size=14, bold=True).pack(anchor="w", padx=20, pady=(20, 12))
        self._label(info, "X 轴：右为正，左为负\nY 轴：前为正，后为负\nZ 轴：本机正方向向下\n\nMPos：GRBL 内部记录的坐标。\nP0：人工标记的物理参考点。\n\nP0 不是硬件回零，也不是编码器原点。重新连接或手工移动后，应先让物理笔架回到 P0，再把坐标解释为实验坐标。\n\n已测量的 XY 安全范围：\nX：−190 到 +190 mm\nY：−90 到 +140 mm\nZ：当前只做相对移动，未建立绝对边界。", size=11, color=self.TEXT, justify="left", anchor="nw", wraplength=440).pack(anchor="nw", padx=20, pady=(0, 20))

    def _draw_causal_chain(self) -> None:
        canvas = getattr(self, "_chain_canvas", None)
        if canvas is None:
            return
        canvas.delete("all")
        width = max(canvas.winfo_width(), 1120)
        stages = CHAIN_STAGES
        gap = 12
        margin = 12
        node_width = (width - margin * 2 - gap * (len(stages) - 1)) / len(stages)
        top, bottom = 7, 63
        for index, stage in enumerate(stages):
            left = margin + index * (node_width + gap)
            right = left + node_width
            active = stage.key == self._active_chain_stage
            fill = self.NAVY if active else "#ffffff"
            outline = self.NAVY if active else self.BORDER
            title_color = "#ffffff" if active else self.TEXT
            detail_color = "#dcecf7" if active else self.MUTED
            if index:
                canvas.create_line(left - gap + 2, 35, left - 3, 35, fill=self.TEAL if active else self.BORDER, width=2, arrow="last")
            canvas.create_rectangle(left, top, right, bottom, fill=fill, outline=outline, width=2 if active else 1)
            canvas.create_text((left + right) / 2, 24, text=stage.title, fill=title_color, font=("Microsoft YaHei UI", 10, "bold"))
            canvas.create_text((left + right) / 2, 46, text=stage.detail, fill=detail_color, font=("Microsoft YaHei UI", 8), width=max(node_width - 12, 70))

    def _draw_coordinate_history(self) -> None:
        canvas = getattr(self, "_trajectory_canvas", None)
        if canvas is None:
            return
        canvas.delete("all")
        width = max(canvas.winfo_width(), 360)
        height = max(canvas.winfo_height(), 150)
        left, top, right, bottom = 42, 22, width - 20, height - 30
        canvas.create_rectangle(left, top, right, bottom, outline=self.BORDER, fill="#ffffff")
        canvas.create_line(left, (top + bottom) / 2, right, (top + bottom) / 2, fill="#e5edf2")
        canvas.create_line((left + right) / 2, top, (left + right) / 2, bottom, fill="#e5edf2")
        canvas.create_text(left, top - 10, text="Y+ 前", fill=self.TEAL, anchor="w", font=("Consolas", 8, "bold"))
        canvas.create_text(left - 5, bottom, text="Y− 后", fill=self.MUTED, anchor="e", font=("Consolas", 8))
        canvas.create_text(right, bottom + 12, text="X+ 右", fill=self.NAVY, anchor="e", font=("Consolas", 8, "bold"))
        canvas.create_text(left, bottom + 12, text="X− 左", fill=self.MUTED, anchor="w", font=("Consolas", 8))
        if not self._position_history:
            canvas.create_text((left + right) / 2, (top + bottom) / 2, text="等待真实 RX 状态帧中的 MPos", fill=self.MUTED, font=("Microsoft YaHei UI", 10))
            return
        x_min, x_max, y_min, y_max = -190.0, 190.0, -90.0, 140.0

        def map_point(position: Position) -> tuple[float, float]:
            x = left + (position.x - x_min) / (x_max - x_min) * (right - left)
            y = bottom - (position.y - y_min) / (y_max - y_min) * (bottom - top)
            return min(max(x, left), right), min(max(y, top), bottom)

        points = [map_point(sample.position) for sample in self._position_history]
        for start, end in zip(points, points[1:]):
            canvas.create_line(*start, *end, fill=self.BLUE, width=2)
        start_x, start_y = points[0]
        end_x, end_y = points[-1]
        canvas.create_oval(start_x - 4, start_y - 4, start_x + 4, start_y + 4, fill=self.NAVY, outline="#ffffff")
        canvas.create_text(start_x + 8, start_y - 8, text="起点", fill=self.NAVY, anchor="w", font=("Microsoft YaHei UI", 8, "bold"))
        canvas.create_oval(end_x - 6, end_y - 6, end_x + 6, end_y + 6, fill=self.TEAL, outline="#ffffff", width=2)
        canvas.create_text(end_x + 9, end_y + 10, text="当前", fill=self.TEAL, anchor="w", font=("Microsoft YaHei UI", 8, "bold"))

    def _render_coordinate_history(self) -> None:
        text = getattr(self, "_position_history_text", None)
        if text is None:
            return
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert("end", "证据范围：仅记录 RX 状态帧中的 MPos；不是编码器实测。\n\n", "notice")
        if not self._position_history:
            text.insert("end", "尚无坐标记录。先连接并读取状态。", "notice")
        for number, sample in enumerate(self._position_history[-8:], start=max(len(self._position_history) - 7, 1)):
            text.insert("end", f"#{number:02d}  {sample.state}  X {sample.position.x:.3f}  Y {sample.position.y:.3f}  Z {sample.position.z:.3f}\n", "sample")
            text.insert("end", f"    {sample.change}\n", "change")
        text.see("end")
        text.configure(state="disabled")
        self._draw_coordinate_history()

    def _draw_coordinates(self) -> None:
        canvas = getattr(self, "_coord_canvas", None)
        if canvas is None:
            return
        canvas.delete("all")
        width = max(canvas.winfo_width(), 450)
        height = max(canvas.winfo_height(), 350)
        left, top, right, bottom = 60, 30, width - 40, height - 55
        canvas.create_rectangle(left, top, right, bottom, outline=self.BORDER, fill="#ffffff")
        for fraction in (0.25, 0.5, 0.75):
            x = left + (right - left) * fraction
            y = top + (bottom - top) * fraction
            canvas.create_line(x, top, x, bottom, fill="#e5edf2")
            canvas.create_line(left, y, right, y, fill="#e5edf2")
        canvas.create_line(left, bottom, right, bottom, fill=self.NAVY, width=2, arrow="last")
        canvas.create_line(left, bottom, left, top, fill=self.NAVY, width=2, arrow="last")
        canvas.create_text(right, bottom + 22, text="X+ 右", fill=self.NAVY, anchor="e", font=("Consolas", 10, "bold"))
        canvas.create_text(left - 8, top - 8, text="Y+ 前", fill=self.NAVY, anchor="e", font=("Consolas", 10, "bold"))
        x_min, x_max, y_min, y_max = -190.0, 190.0, -90.0, 140.0
        px = left + (self._current_position.x - x_min) / (x_max - x_min) * (right - left)
        py = bottom - (self._current_position.y - y_min) / (y_max - y_min) * (bottom - top)
        px = min(max(px, left), right)
        py = min(max(py, top), bottom)
        canvas.create_line(px - 14, py, px + 14, py, fill=self.TEAL, width=2)
        canvas.create_line(px, py - 14, px, py + 14, fill=self.TEAL, width=2)
        canvas.create_oval(px - 6, py - 6, px + 6, py + 6, fill=self.TEAL, outline="#ffffff", width=2)
        canvas.create_text(px + 12, py - 12, text="当前 MPos", fill=self.TEAL, anchor="w", font=("Microsoft YaHei UI", 9, "bold"))

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
            self._state.set(f"已提交真实动作 · {axis}{distance_mm:g} mm · 等待 CALL/TX/RX")
            self._worker.request_jog(axis, distance_mm, feed_mm_min)

    def _drain_events(self) -> None:
        while True:
            try:
                kind, payload = self._events.get_nowait()
            except queue.Empty:
                break
            if kind == "trace":
                event = payload
                self._sequence += 1
                explanation = explain_trace_event(event)
                self._history = (self._history + [(self._sequence, event, explanation)])[-30:]
                self._render_detail(explanation, event)
                self._render_flow()
                if event.kind == "RX" and event.text.strip().startswith("<"):
                    self._update_status(event.text)
            elif kind == "connected":
                self._connection.set("已连接")
                self._state.set(f"已连接 {payload} · 已执行首次只读状态查询")
                self._status_button.configure(state="normal")
                for button in self._motion_buttons:
                    button.configure(state="normal")
            elif kind == "status":
                self._update_status(payload)
            elif kind == "motion_done":
                command = payload
                self._state.set(f"动作已完成 · {command.axis}{command.distance_mm:g} mm · 请独立观察机械运动")
            elif kind == "error":
                self._connection.set("错误")
                self._state.set(f"错误 · {payload}")
                self._detail_heading.set("控制器暂停了本次动作")
                self._detail_plain.set("请检查通信流水中的最后一条错误，再检查电源、端口和机械余量。")
                self._detail_technical.set(str(payload))
            elif kind == "disconnected":
                self._connection.set("未连接")
                self._status_button.configure(state="disabled")
                for button in self._motion_buttons:
                    button.configure(state="disabled")
                if self._worker is not None and not self._worker.is_running:
                    self._connect_button.configure(state="normal")
        self._event_counter.set(f"{self._sequence} 条真实事件")
        self._root.after(100, self._drain_events)

    def _update_status(self, status: str) -> None:
        try:
            explanation = explain_status(status)
            previous = self._position_history[-1].position if self._position_history else None
            sample = record_coordinate_status(status, previous)
        except ValueError:
            self._grbl_state.set("未知")
            return
        self._grbl_state.set(explanation.state)
        self._current_position = explanation.position
        self._position.set(f"X {explanation.position.x:.1f}   Y {explanation.position.y:.1f}   Z {explanation.position.z:.1f} mm")
        self._coord_plain.set(explanation.plain)
        self._coord_technical.set(explanation.technical)
        self._draw_coordinates()
        if previous is None or sample.position != previous or sample.state != self._position_history[-1].state:
            self._position_history = (self._position_history + [sample])[-24:]
            self._render_coordinate_history()

    def _render_detail(self, explanation: TeachingExplanation, event: TraceEvent) -> None:
        self._active_chain_stage = explanation.stage if explanation.stage in {stage.key for stage in CHAIN_STAGES} else None
        title = next((stage.title for stage in CHAIN_STAGES if stage.key == self._active_chain_stage), "串口事件")
        self._chain_summary.set(f"当前真实阶段：{title}。{explanation.plain}")
        self._draw_causal_chain()
        self._detail_stage.set(f"阶段：{explanation.stage} · {event.kind}")
        self._detail_heading.set(explanation.heading)
        self._detail_plain.set(explanation.plain)
        self._detail_technical.set(explanation.technical)
        try:
            self._detail_fields.set(format_frame_fields(event))
        except ValueError as exc:
            self._detail_fields.set(f"字段解析失败：{exc}")
        self._detail_code.set(explanation.code)
        self._detail_raw.set(f"{event.kind}  |  {event.text!r}")

    def _render_flow(self) -> None:
        self._flow.configure(state="normal")
        self._flow.delete("1.0", "end")
        if not self._history:
            self._flow.insert("end", "尚无真实通信\n", "summary")
            self._flow.insert("end", f"连接 {self._port} 后，先执行一次只读状态查询。下面的说明不是通信数据：\n\n", "payload")
            self._flow.insert("end", "CALL / Python function call：程序内部开始执行，尚未写入串口。\n", "summary")
            self._flow.insert("end", "TX / Transmit：电脑把字节发送给 GRBL。\n", "summary")
            self._flow.insert("end", "RX / Receive：电脑从 GRBL 接收返回字节。\n", "summary")
            self._flow.insert("end", "ok 只代表已接收；最终 RX Idle 才表示 GRBL 报告本轮控制结束。\n", "summary")
        for sequence, event, _explanation in self._history:
            header, payload, summary = format_stream_row(sequence, event)
            tag = "call" if event.kind == "CALL" else "tx" if event.kind == "TX" else "rx"
            self._flow.insert("end", f"{header}\n", tag)
            self._flow.insert("end", f"    {payload}\n", "payload")
            self._flow.insert("end", f"    {summary}\n\n", "summary")
        self._flow.see("end")
        self._flow.configure(state="disabled")

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
