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
        "Windows 会给 USB 串口设备分配一个逻辑名称，例如 COM4。电脑先把数据交给 CH340 USB-UART 桥接芯片，再由它转换成 Arduino 能读的 UART 电平；返回数据沿相反方向回到 Python。COMx 只是 Windows 的设备地址，不是 GRBL，也不是网络端口。换 USB 插口、换电脑或重装驱动后，编号可能变化；程序必须使用设备管理器当前显示的 COMx，并以 115200、8-N-1 打开。",
        "COMx · 115200 baud · 8-N-1",
    ),
    ProtocolGuideEntry(
        "COMx",
        "Windows 设备地址",
        "例如 COM4：Python 找到 USB 串口设备的入口名称。",
        "COM4 不是固件名称，也不是电机驱动器名称。启动参数 --port COM4 只是在告诉 pySerial 打开哪个 Windows 串口；如果设备管理器显示的是 COM7，程序就必须改用 COM7。界面显示的端口来自启动参数，不会自动替换成别的编号。",
        "python -m communication.dayuwriter.grbl_monitor --port COM4",
    ),
    ProtocolGuideEntry(
        "CH340",
        "USB-UART 桥接芯片",
        "把 USB 数据转换成 Arduino UART 串口数据的硬件。",
        "CH340 负责电脑与 Arduino 串口电平之间的转换，不负责解析 G-code、不规划运动，也不产生电机脉冲。驱动正常时，Windows 才会在设备管理器中显示 USB-SERIAL CH340 (COMx)。",
        "电脑 USB → CH340 → Arduino UART",
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
        "运行在 Arduino 上的开源嵌入式 G-code 解析与运动控制固件。",
        "GRBL 是烧录在 Arduino UNO 微控制器中的固件。它读取串口文本，检查 $J= 等指令是否合法，规划速度与加速度，生成 STEP/DIR 步进脉冲交给 A4988，并维护 Idle、Jog、Hold、Alarm 等状态和 MPos 记录。它不做目标识别、不理解相机像素、不读取编码器真实位置，也不负责 USB 驱动；因此 MPos 只能证明 GRBL 的内部记录，不能单独证明滑台没有丢步。",
        "Arduino UNO + GRBL 1.1f",
    ),
    ProtocolGuideEntry(
        "STEP/DIR",
        "电机驱动信号",
        "GRBL 发给 A4988 的两类数字信号。",
        "STEP 的每个脉冲通常对应一个微步动作，DIR 表示正反方向。A4988 根据这些信号给步进电机绕组通电；同步带、导轨和丝杆再把旋转变成 X/Y/Z 机械位移。",
        "GRBL → STEP/DIR → A4988 → 42 步进电机",
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


@dataclass(frozen=True)
class SignalPathNode:
    """One visible station in the command, electrical, and return path."""

    key: str
    title: str
    subtitle: str
    detail: str
    payload: str
    tone: str


SIGNAL_PATH_NODES = (
    SignalPathNode(
        "python",
        "Python 控制器",
        "软件决策层",
        "检查已知边界，生成一次受限 Jog 请求。",
        "controller.jog(...)",
        "software",
    ),
    SignalPathNode(
        "pyserial",
        "pySerial",
        "串口软件接口",
        "把 Unicode 指令编码成 bytes，写入 Windows 串口。",
        "write(bytes)",
        "software",
    ),
    SignalPathNode(
        "windows_com",
        "Windows COMx",
        "操作系统设备端点",
        "例如 COM4：程序找到 USB 串口设备的入口。",
        "115200 · 8-N-1",
        "transport",
    ),
    SignalPathNode(
        "ch340",
        "CH340",
        "USB-UART 桥",
        "把 USB 传输转换为 Arduino UART 串行电平。",
        "USB bytes ↔ UART",
        "transport",
    ),
    SignalPathNode(
        "grbl",
        "Arduino + GRBL",
        "固件与运动规划",
        "解析 G-code/Jog，规划速度，并维护 MPos 与状态。",
        "$J=G91 G21 X5 F100",
        "firmware",
    ),
    SignalPathNode(
        "step_dir",
        "STEP / DIR",
        "数字脉冲信号",
        "STEP 脉冲计步；DIR 电平决定正反方向。",
        "pulse + direction",
        "pulse",
    ),
    SignalPathNode(
        "a4988",
        "A4988",
        "功率驱动层",
        "按 STEP/DIR 给电机绕组提供受控电流与细分。",
        "coil current",
        "motion",
    ),
    SignalPathNode(
        "mechanics",
        "电机与滑台",
        "机械执行层",
        "电机转动，经同步带、导轨或丝杆形成 X/Y/Z 位移。",
        "physical motion",
        "motion",
    ),
    SignalPathNode(
        "return",
        "RX 状态证据",
        "返回路径",
        "GRBL 把状态帧经 UART、CH340、COMx 回传给 Python。",
        "<Idle|MPos:...>",
        "return",
    ),
)


def signal_path_nodes() -> tuple[SignalPathNode, ...]:
    """Expose the fixed teaching model without fabricating serial events."""

    return SIGNAL_PATH_NODES


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


class ScrollableContent(tk.Frame):
    """A vertical page viewport with a visible, draggable scrollbar."""

    def __init__(self, parent: tk.Widget, *, background: str) -> None:
        super().__init__(parent, bg=background)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, bg=background, bd=0, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollbar.grid(row=0, column=1, sticky="ns", padx=(4, 0))
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.content = tk.Frame(self.canvas, bg=background)
        self._content_window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", self._update_scroll_region)
        self.canvas.bind("<Configure>", self._fit_content_width)
        self.canvas.bind("<MouseWheel>", self._mousewheel)

    def _update_scroll_region(self, _event: tk.Event[tk.Misc]) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _fit_content_width(self, event: tk.Event[tk.Misc]) -> None:
        self.canvas.itemconfigure(self._content_window, width=event.width)

    def _mousewheel(self, event: tk.Event[tk.Misc]) -> str:
        self.canvas.yview_scroll(-int(event.delta / 120), "units")
        return "break"


class ProtocolMonitorApp:
    """A calm three-page desktop classroom for real GRBL events."""

    BG = "#eaf0f1"
    SURFACE = "#fdfefe"
    SURFACE_ALT = "#f3f7f7"
    BORDER = "#c7d3d5"
    TEXT = "#1d3036"
    MUTED = "#5f7378"
    NAVY = "#21343b"
    TEAL = "#007d77"
    BLUE = "#2769a8"
    PURPLE = "#7555a2"
    GREEN = "#258255"
    AMBER = "#b97917"
    RED = "#b94842"
    CYAN = "#147f98"
    CORAL = "#bd5d3d"

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
        style.map("Action.TButton", background=[("active", "#374151"), ("disabled", "#c7cdd6")])
        style.configure("Move.TButton", background=self.SURFACE_ALT, foreground=self.TEXT, padding=(8, 8), font=("Microsoft YaHei UI", 10))
        style.map("Move.TButton", background=[("active", "#eef2ff"), ("disabled", "#edf0f3")])
        style.configure("TNotebook", background=self.BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#eef1f4", foreground=self.MUTED, padding=(18, 9), font=("Microsoft YaHei UI", 10, "bold"))
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
        tk.Label(header, text="先看真实链路，再看每一行 TX/RX，最后用 MPos 和现场观察确认结果。", bg=self.BG, fg=self.MUTED, font=("Microsoft YaHei UI", 11)).grid(row=2, column=0, sticky="w", pady=(3, 0))
        metrics = tk.Frame(header, bg=self.BG)
        metrics.grid(row=0, column=1, rowspan=3, sticky="e")
        self._metric(metrics, "Windows 串口", self._port, 0, self.NAVY)
        self._metric(metrics, "连接", self._connection, 1, self.TEAL)
        self._metric(metrics, "GRBL", self._grbl_state, 2, self.AMBER)
        self._metric(metrics, "坐标", self._position, 3, self.BLUE)
        tk.Label(metrics, textvariable=self._event_counter, bg=self.BG, fg=self.MUTED, font=("Consolas", 9)).grid(row=1, column=0, columnspan=4, sticky="e", pady=(7, 0))
        tk.Label(metrics, text="端口来自启动参数 --port；GRBL 固件运行在 Arduino 内部。", bg=self.BG, fg=self.MUTED, font=("Microsoft YaHei UI", 8)).grid(row=2, column=0, columnspan=4, sticky="e", pady=(2, 0))

    def _metric(self, parent: tk.Widget, title: str, value: tk.Variable | str, column: int, color: str) -> None:
        block = tk.Frame(parent, bg=self.BG)
        block.grid(row=0, column=column, padx=(24 if column else 0, 0), sticky="e")
        tk.Label(block, text=title, bg=self.BG, fg=self.MUTED, font=("Microsoft YaHei UI", 8, "bold")).pack(anchor="e")
        kwargs = {"textvariable": value} if isinstance(value, tk.Variable) else {"text": value}
        tk.Label(block, bg=self.BG, fg=color, font=("Consolas", 11, "bold"), **kwargs).pack(anchor="e")

    def _build_live_page(self, parent: tk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        self._live_scroll = ScrollableContent(parent, background=self.BG)
        self._live_scroll.grid(row=0, column=0, sticky="nsew")
        content = self._live_scroll.content
        content.columnconfigure(0, weight=0, minsize=285)
        content.columnconfigure(1, weight=1, minsize=640)
        content.columnconfigure(2, weight=0, minsize=410)
        content.rowconfigure(0, weight=0)
        content.rowconfigure(1, weight=1)
        self._build_causal_chain(content)
        self._build_controls(content, 1)
        self._build_stream(content, 1)
        self._build_current_detail(content, 1)

    def _build_causal_chain(self, parent: tk.Frame) -> None:
        band = tk.Frame(parent, bg=self.SURFACE, highlightbackground=self.BORDER, highlightthickness=1)
        band.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 14))
        band.columnconfigure(0, weight=1)
        tk.Label(band, text="从一条 Python 指令到滑台位移：真实信号路径", bg=self.SURFACE, fg=self.NAVY, font=("Microsoft YaHei UI", 15, "bold"), anchor="w").grid(row=0, column=0, sticky="w", padx=20, pady=(16, 0))
        tk.Label(band, text="通信协议不是‘一根线’：它同时约定数据内容、字节结束方式、传输速度、电气接口、状态含义与应答顺序。", bg=self.SURFACE, fg=self.MUTED, font=("Microsoft YaHei UI", 10), anchor="w").grid(row=1, column=0, sticky="w", padx=20, pady=(2, 8))
        self._chain_canvas = tk.Canvas(band, height=420, bg=self.SURFACE, bd=0, highlightthickness=0)
        self._chain_canvas.grid(row=2, column=0, sticky="ew", padx=12)
        self._chain_canvas.bind("<Configure>", lambda _event: self._draw_causal_chain())
        tk.Label(band, text="协议数据：ASCII G-code/Jog + LF（指令结束）  |  链路设置：115200 baud · 8-N-1  |  实时查询：?（单个字节，无换行）", bg=self.SURFACE_ALT, fg=self.TEXT, font=("Consolas", 9), anchor="w", justify="left", wraplength=1400).grid(row=3, column=0, sticky="ew", padx=20, pady=(4, 3))
        tk.Label(band, textvariable=self._chain_summary, bg=self.SURFACE, fg=self.TEXT, font=("Microsoft YaHei UI", 9), anchor="w", justify="left", wraplength=1400).grid(row=4, column=0, sticky="ew", padx=20, pady=(2, 14))
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
        self._label(controls, f"Windows 端口：{self._port}\n115200 baud · 8-N-1 · 无流控\nP0 是手动参考点，不是编码器原点。", size=9, color=self.MUTED, justify="left").grid(row=12, column=0, sticky="w", padx=16, pady=(0, 14))
        glossary = tk.Frame(controls, bg=self.SURFACE_ALT, highlightbackground=self.BORDER, highlightthickness=1)
        glossary.grid(row=13, column=0, sticky="ew", padx=14, pady=(0, 16))
        tk.Label(glossary, text="COMx / CH340 是什么？", bg=self.SURFACE_ALT, fg=self.NAVY, font=("Microsoft YaHei UI", 10, "bold"), anchor="w").pack(anchor="w", padx=12, pady=(9, 4))
        tk.Label(glossary, text=f"COM4 只是一个例子；本次启动配置是 {self._port}。Windows 给 USB 设备分配 COMx 名称，CH340 把 USB 数据转换成 Arduino UART。\n\nCOMx 不等于 GRBL：COMx 是电脑端入口，GRBL 是控制板里的固件。换 USB 插口或驱动后，编号可能变化。", bg=self.SURFACE_ALT, fg=self.TEXT, font=("Microsoft YaHei UI", 9), justify="left", anchor="w", wraplength=245).pack(anchor="w", padx=12, pady=(0, 10))
        glossary2 = tk.Frame(controls, bg=self.SURFACE, highlightbackground=self.BORDER, highlightthickness=1)
        glossary2.grid(row=14, column=0, sticky="ew", padx=14, pady=(0, 12))
        tk.Label(glossary2, text="术语速读：每个词在链路中的位置", bg=self.SURFACE, fg=self.NAVY, font=("Microsoft YaHei UI", 10, "bold"), anchor="w").pack(anchor="w", padx=12, pady=(9, 4))
        tk.Label(glossary2, text="CALL / function call：Python 内部调用，还未出电脑。\nTX / Transmit：电脑 → GRBL，发送字节。\nRX / Receive：GRBL → 电脑，返回字节。\nok：这一行已被接受，不等于电机停止。\nIdle：GRBL 报告本轮控制周期结束。", bg=self.SURFACE, fg=self.TEXT, font=("Microsoft YaHei UI", 9), justify="left", anchor="w", wraplength=245).pack(anchor="w", padx=12, pady=(0, 10))
        grbl = tk.Frame(controls, bg=self.SURFACE, highlightbackground=self.BORDER, highlightthickness=1)
        grbl.grid(row=15, column=0, sticky="ew", padx=14, pady=(0, 12))
        tk.Label(grbl, text="GRBL 是什么？", bg=self.SURFACE, fg=self.TEAL, font=("Microsoft YaHei UI", 11, "bold"), anchor="w").pack(anchor="w", padx=12, pady=(11, 4))
        tk.Label(grbl, text="它是烧录在 Arduino UNO 里的开源运动控制固件，不是电脑软件，也不是 A4988 电机驱动板。\n\n真实链路：Python → USB/CH340 → GRBL → STEP/DIR 脉冲 → A4988 → 步进电机。\n\nGRBL 负责：解析 $J= 等指令、控制速度、生成步进脉冲、记录 MPos、回报 Idle/Jog。\n\nGRBL 不负责：识别杂草、理解相机画面、读取编码器真实位置、自动知道人工 P0。", bg=self.SURFACE, fg=self.TEXT, font=("Microsoft YaHei UI", 9), justify="left", anchor="w", wraplength=245).pack(anchor="w", padx=12, pady=(0, 11))
        rule = tk.Frame(controls, bg=self.SURFACE_ALT, highlightbackground=self.BORDER, highlightthickness=1)
        rule.grid(row=16, column=0, sticky="ew", padx=14, pady=(0, 16))
        tk.Label(rule, text="怎样判断一次移动", bg=self.SURFACE_ALT, fg=self.BLUE, font=("Microsoft YaHei UI", 9, "bold"), anchor="w").pack(anchor="w", padx=12, pady=(9, 4))
        tk.Label(rule, text="1. TX：电脑确实发出指令。\n2. RX ok：GRBL 确实接受指令。\n3. RX Jog：GRBL 仍在运动。\n4. RX Idle：GRBL 报告控制周期结束。\n5. 最后还要肉眼确认机构真实位移。", bg=self.SURFACE_ALT, fg=self.TEXT, font=("Microsoft YaHei UI", 9), justify="left", anchor="w").pack(anchor="w", padx=12, pady=(0, 10))

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
        self._flow = scrolledtext.ScrolledText(panel, height=14, wrap="word", state="disabled", bg="#f8faf9", fg=self.TEXT, relief="flat", bd=0, padx=14, pady=14, font=("Consolas", 10), spacing1=2, spacing3=5)
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
        self._position_history_text = scrolledtext.ScrolledText(history, height=9, wrap="word", state="disabled", bg="#f8faf9", fg=self.TEXT, relief="flat", bd=0, padx=12, pady=10, font=("Consolas", 9), spacing1=2, spacing3=3)
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
        tk.Label(parent, text=f"当前显示端口：{self._port}。端口由启动参数 --port 传入；本页解释的是实际设备链路，不会把 COMx 当成 GRBL。", bg=self.BG, fg=self.MUTED, font=("Microsoft YaHei UI", 11), anchor="w").grid(row=1, column=0, sticky="w", padx=20, pady=(0, 2))
        text = scrolledtext.ScrolledText(parent, wrap="word", bg="#ffffff", fg=self.TEXT, relief="flat", bd=0, padx=28, pady=22, font=("Microsoft YaHei UI", 11), spacing1=2, spacing3=5)
        text.grid(row=2, column=0, sticky="nsew", padx=20, pady=(16, 20))
        text.tag_configure("section", foreground=self.NAVY, font=("Microsoft YaHei UI", 15, "bold"), spacing1=13)
        text.tag_configure("term", foreground=self.TEAL, font=("Microsoft YaHei UI", 12, "bold"), spacing1=8)
        text.tag_configure("body", foreground=self.TEXT)
        text.tag_configure("code", foreground=self.AMBER, font=("Consolas", 10))
        text.insert("end", "一、先分清三个最容易混淆的名字\n", "section")
        for term, detail in (
            ("COMx · Windows 设备地址", f"本次界面配置为 {self._port}。它只是 Windows 给 USB 串口设备分配的逻辑名称，Python 用 --port 参数打开它。换插口、换电脑或重新安装驱动后，COM 编号可能变化。"),
            ("CH340 · USB-UART 桥接芯片", "它位于 USB 与 Arduino 串口之间，只做数据格式和电平转换。CH340 不解析 G-code、不控制速度、不产生电机脉冲。驱动正常时，设备管理器会显示 USB-SERIAL CH340 (COMx)。"),
            ("GRBL · Arduino 内的运动固件", "它烧录在 Arduino UNO 的微控制器里，负责读取串口文本、解析 G-code/Jog、规划运动、生成 STEP/DIR 脉冲、维护状态和 MPos。GRBL 不是 COM 端口，也不是 A4988 驱动板。"),
        ):
            text.insert("end", f"{term}\n", "term")
            text.insert("end", f"{detail}\n\n", "body")

        text.insert("end", "二、从按钮到机械运动的完整因果链\n", "section")
        chain = (
            ("1  人的动作", "点击 X/Y/Z 按钮；按钮本身不直接接触电机，只产生一个软件事件。"),
            ("2  Python 函数", "界面调用 GrblWorker.request_jog，再由持久 GrblController.jog(...) 执行。持久连接避免每次动作都重新打开串口。"),
            ("3  pySerial", "Python 把 ASCII 文本和换行符写入 Windows 的当前 COMx 端点。这里的 TX 是 Transmit，表示电脑发送方向。"),
            ("4  USB 总线", "USB 数据到达 CH340；Windows 驱动把它呈现为 COMx，程序不需要直接操作 USB 电气信号。"),
            ("5  CH340 转换", "CH340 把 USB 数据转换成 Arduino UART 可以接收的串行字节，再送入 Arduino 的 RX 引脚。"),
            ("6  Arduino UART", "Arduino 按 115200、8-N-1 的串口约定逐字节接收；这是传输格式，不是运动算法。"),
            ("7  GRBL 解析", "GRBL 识别 $J=G91 G21 X5 F100：$J= 表示 Jog，G91 表示相对移动，G21 表示毫米，X5 是增量 5 mm，F100 是速度 100 mm/min。"),
            ("8  GRBL 规划", "固件检查边界、速度和当前状态，安排加速度和每一步的时间。它把文本意图变成时序动作。"),
            ("9  STEP/DIR", "GRBL 输出 STEP 脉冲和 DIR 方向信号。STEP 的脉冲频率影响速度，DIR 的电平决定正反方向。"),
            ("10  A4988", "A4988 接收 STEP/DIR 并给步进电机绕组通电；细分开关会影响每个脉冲对应的角度。"),
            ("11  机械机构", "42 步进电机带动同步带、直线导轨或 Z 轴丝杆，最终让笔架产生 X/Y/Z 位移。"),
            ("12  GRBL 状态", "GRBL 同时维护 Idle、Jog、Hold、Alarm 等状态，并更新内部 MPos。MPos 是估算/记录值，不是编码器实测。"),
            ("13  返回电脑", "GRBL 通过 Arduino UART → CH340 → USB → Windows COMx 返回 RX 字节；Python 读取后更新本页的流水、状态和坐标历程。"),
        )
        for title, detail in chain:
            text.insert("end", f"{title}\n", "term")
            text.insert("end", f"{detail}\n\n", "body")

        text.insert("end", "三、一条真实点动会看到什么\n", "section")
        for line in (
            ("CALL / Python function call", "程序内部开始执行，尚未离开电脑；例如 controller.jog(JogCommand(...))。"),
            ("TX  $J=G91 G21 X5 F100\\n", "电脑向 GRBL 发送一行 ASCII 文本。换行符告诉 GRBL 这一行已经结束。"),
            ("RX  ok", "GRBL 已接收并接受这一行，可能已经排入运动规划；ok 不是电机停止证明。"),
            ("TX  ?", "电脑发送 GRBL 实时状态查询字符。它不需要换行，也不会让机器移动。"),
            ("RX  <Jog|MPos:...>", "GRBL 报告仍处于 Jog；MPos 后三个数依次是 X、Y、Z 的内部坐标。"),
            ("RX  <Idle|MPos:...>", "GRBL 报告回到 Idle，说明控制器认为本轮运动周期结束；还要肉眼观察机构是否真的移动到位。"),
        ):
            text.insert("end", f"{line[0]}\n", "code" if line[0].startswith(("TX", "RX")) else "term")
            text.insert("end", f"{line[1]}\n\n", "body")

        text.insert("end", "四、GRBL 负责什么、不负责什么\n", "section")
        text.insert("end", "GRBL 负责：\n", "term")
        text.insert("end", "• 解析有限的 G-code/Jog 文本并返回 ok/error。\n• 管理 Idle、Jog、Hold、Alarm 等运动状态。\n• 计算速度、加速度和步进时序。\n• 输出 STEP/DIR 信号给 A4988。\n• 维护 MPos，并通过状态帧返回给上位机。\n\n", "body")
        text.insert("end", "GRBL 不负责：\n", "term")
        text.insert("end", "• 不识别相机图像、杂草或目标物品。\n• 不理解像素坐标，也不把相机坐标自动转换成机器坐标。\n• 不读取闭环编码器，不能独立发现丢步。\n• 不知道人工标记的 P0，也不替代硬件回零。\n• 不安装 CH340 驱动，也不决定 Windows 的 COM 编号。\n\n", "body")

        text.insert("end", "五、如何读懂一条状态帧\n", "section")
        text.insert("end", "示例：<Jog|MPos:0.225,0.000,0.000|FS:100,0|Pn:P>\n", "code")
        for field, detail in (
            ("<  >", "尖括号是状态帧边界，表示这不是普通 G-code 回显。"),
            ("Jog", "State / 机器状态：GRBL 认为当前正在点动。"),
            ("MPos:0.225,0.000,0.000", "Machine Position / 机器位置：X=0.225 mm、Y=0.000 mm、Z=0.000 mm；这是固件内部记录。"),
            ("FS:100,0", "Feed rate and Spindle speed：进给速度 100 mm/min、主轴速度 0 RPM；本写字机主要关注进给。"),
            ("Pn:P", "Pin State：P 表示探针输入被报告为触发；它不是‘已经碰到目标’的视觉结论，做 Z 标定前必须单独处理。"),
        ):
            text.insert("end", f"{field}\n", "term")
            text.insert("end", f"{detail}\n\n", "body")

        text.insert("end", "六、证据强度：什么可以证明什么\n", "section")
        text.insert("end", "TX 只能证明电脑确实写出了指令；RX ok 只能证明 GRBL 接受了指令；RX Jog 说明 GRBL 报告仍在运动；RX Idle 说明 GRBL 报告控制周期结束；MPos 只能证明固件内部位置记录变化。最终要把通信证据、坐标变化和现场肉眼观察放在一起，才能说‘这次移动完成且方向正确’。断电、手推、复位或疑似丢步后，必须重新把笔架物理对齐到 P0。\n\n", "body")

        text.insert("end", "七、这条链路怎样连接到后续视觉功能\n", "section")
        text.insert("end", "相机先得到像素坐标；深度相机还可以得到相机坐标。之后必须用独立标定得到‘相机坐标 → P0/机器坐标’的变换，并用已知点验证误差。视觉算法只负责提出目标位置，Python 控制器负责检查边界、生成受限 Jog，GRBL 负责执行脉冲；相机坐标不能直接塞进 GRBL。\n\n", "body")

        text.insert("end", "八、术语词典（可在实时页对照）\n", "section")
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
        width = max(canvas.winfo_width(), 1240)
        node_width = min(236, (width - 56) / 5 - 14)
        gap = (width - 40 - node_width * 5) / 4
        top_y, top_height = 67, 104
        nodes = signal_path_nodes()
        tone_color = {
            "software": self.BLUE,
            "transport": self.CYAN,
            "firmware": self.TEAL,
            "pulse": self.AMBER,
            "motion": self.CORAL,
            "return": self.PURPLE,
        }
        stage_to_node = {
            "python": "python",
            "command": "pyserial",
            "accepted": "grbl",
            "poll": "pyserial",
            "running": "grbl",
            "complete": "return",
        }
        active_key = stage_to_node.get(self._active_chain_stage or "")

        canvas.create_text(22, 20, text="01  命令数据从电脑进入控制板", fill=self.BLUE, anchor="w", font=("Consolas", 10, "bold"))
        canvas.create_text(22, 40, text="每个方框都标出：谁在工作、它拿到或输出什么、它不负责什么。", fill=self.MUTED, anchor="w", font=("Microsoft YaHei UI", 9))

        def draw_node(node: SignalPathNode, left: float, top: float, card_width: float, card_height: float) -> tuple[float, float]:
            color = tone_color[node.tone]
            active = node.key == active_key
            fill = color if active else self.SURFACE_ALT
            outline = color
            main = "#ffffff" if active else self.TEXT
            minor = "#eaf7f6" if active else self.MUTED
            canvas.create_rectangle(left, top, left + card_width, top + card_height, fill=fill, outline=outline, width=2 if active else 1)
            canvas.create_rectangle(left, top, left + 7, top + card_height, fill=color, outline=color)
            canvas.create_text(left + 18, top + 17, text=node.title, fill=main, anchor="w", font=("Microsoft YaHei UI", 11, "bold"))
            canvas.create_text(left + 18, top + 37, text=node.subtitle, fill=minor, anchor="w", font=("Microsoft YaHei UI", 8, "bold"))
            canvas.create_text(left + 18, top + 61, text=node.detail, fill=main, anchor="w", font=("Microsoft YaHei UI", 8), width=card_width - 34)
            canvas.create_rectangle(left + 14, top + card_height - 25, left + card_width - 13, top + card_height - 7, fill="#ffffff" if active else "#e8eef0", outline="")
            canvas.create_text(left + 20, top + card_height - 16, text=node.payload, fill=color if not active else self.NAVY, anchor="w", font=("Consolas", 8, "bold"), width=card_width - 42)
            return left + card_width / 2, top + card_height / 2

        top_centers: list[tuple[float, float]] = []
        for index, node in enumerate(nodes[:5]):
            left = 20 + index * (node_width + gap)
            center = draw_node(node, left, top_y, node_width, top_height)
            top_centers.append(center)
            if index:
                previous_x, previous_y = top_centers[index - 1]
                canvas.create_line(previous_x + node_width / 2 - 3, previous_y, center[0] - node_width / 2 + 3, center[1], fill=self.BLUE, width=3, arrow="last")

        canvas.create_text(22, 196, text="02  GRBL 把文本协议转换成可驱动机械的数字脉冲", fill=self.AMBER, anchor="w", font=("Consolas", 10, "bold"))
        canvas.create_text(22, 216, text="此处不再传输 G-code 文本：STEP 是计步脉冲，DIR 是方向电平；线路从右向左继续。", fill=self.MUTED, anchor="w", font=("Microsoft YaHei UI", 9))
        actuation_width = min(270, node_width + 24)
        actuation_gap = 20
        actuation_y, actuation_height = 238, 98
        grbl_x, _grbl_y = top_centers[-1]
        step_left = min(max(20 + actuation_width * 2 + actuation_gap * 2, grbl_x - actuation_width / 2), width - 20 - actuation_width)
        a4988_left = step_left - actuation_width - actuation_gap
        mechanics_left = a4988_left - actuation_width - actuation_gap
        actuation_layout = (
            (nodes[7], mechanics_left),
            (nodes[6], a4988_left),
            (nodes[5], step_left),
        )
        actuation_centers = {node.key: draw_node(node, left, actuation_y, actuation_width, actuation_height) for node, left in actuation_layout}
        step_x, step_y = actuation_centers["step_dir"]
        a4988_x, a4988_y = actuation_centers["a4988"]
        mechanics_x, mechanics_y = actuation_centers["mechanics"]
        canvas.create_line(step_x - actuation_width / 2 - 3, step_y, a4988_x + actuation_width / 2 + 3, a4988_y, fill=self.CORAL, width=3, arrow="last")
        canvas.create_line(a4988_x - actuation_width / 2 - 3, a4988_y, mechanics_x + actuation_width / 2 + 3, mechanics_y, fill=self.CORAL, width=3, arrow="last")
        canvas.create_line(grbl_x, top_y + top_height + 4, step_x, step_y - actuation_height / 2 - 4, fill=self.AMBER, width=3, arrow="last")
        canvas.create_text(grbl_x + 10, top_y + top_height + 23, text="文本 → 脉冲", fill=self.AMBER, anchor="w", font=("Microsoft YaHei UI", 8, "bold"))

        return_node = nodes[-1]
        return_top, return_height = 354, 50
        return_width = min(740, width - 300)
        return_left = 80
        return_color = tone_color[return_node.tone]
        return_active = active_key == "return"
        canvas.create_rectangle(return_left, return_top, return_left + return_width, return_top + return_height, fill=return_color if return_active else "#f2eef8", outline=return_color, width=2 if return_active else 1)
        canvas.create_text(return_left + 16, return_top + 16, text="03  返回证据 / RX", fill="#ffffff" if return_active else self.PURPLE, anchor="w", font=("Microsoft YaHei UI", 10, "bold"))
        canvas.create_text(return_left + 16, return_top + 34, text="GRBL → Arduino UART → CH340 → USB → Windows COMx → pySerial.readline() → 实时界面", fill="#ffffff" if return_active else self.TEXT, anchor="w", font=("Microsoft YaHei UI", 8), width=return_width - 150)
        canvas.create_text(return_left + return_width - 14, return_top + 25, text=return_node.payload, fill="#ffffff" if return_active else return_color, anchor="e", font=("Consolas", 8, "bold"))
        grbl_right = grbl_x + node_width / 2
        return_bus_x = width - 24
        canvas.create_line(grbl_right + 4, top_y + top_height / 2, return_bus_x, top_y + top_height / 2, return_bus_x, return_top + return_height / 2, return_left + return_width + 4, return_top + return_height / 2, fill=return_color, width=2, arrow="last")
        canvas.create_text(return_bus_x - 8, return_top - 9, text="状态回传走 UART/USB，不经过 A4988", fill=self.PURPLE, anchor="e", font=("Microsoft YaHei UI", 8))

    def _draw_coordinate_history(self) -> None:
        canvas = getattr(self, "_trajectory_canvas", None)
        if canvas is None:
            return
        canvas.delete("all")
        width = max(canvas.winfo_width(), 360)
        height = max(canvas.winfo_height(), 150)
        left, top, right, bottom = 42, 22, width - 20, height - 30
        canvas.create_rectangle(left, top, right, bottom, outline=self.BORDER, fill="#ffffff")
        canvas.create_line(left, (top + bottom) / 2, right, (top + bottom) / 2, fill="#e2e9e8")
        canvas.create_line((left + right) / 2, top, (left + right) / 2, bottom, fill="#e2e9e8")
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
            canvas.create_line(x, top, x, bottom, fill="#e2e9e8")
            canvas.create_line(left, y, right, y, fill="#e2e9e8")
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
