from communication.dayuwriter.grbl_controller import TraceEvent
import pytest

from communication.dayuwriter.grbl_monitor import (
    BUTTON_ACTIONS,
    ScrollableContent,
    record_coordinate_status,
    describe_trace_event,
    explain_status,
    explain_trace_event,
    event_stage,
    format_trace_event,
    format_stream_row,
    format_frame_fields,
    parse_status_fields,
    protocol_guide,
    validate_monitor_motion,
)


def test_scrollable_content_exposes_a_canvas_and_vertical_scrollbar() -> None:
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.withdraw()
    try:
        content = ScrollableContent(root, background="#ffffff")
        assert isinstance(content.canvas, tk.Canvas)
        assert isinstance(content.scrollbar, ttk.Scrollbar)
        assert content.content.master is content.canvas
    finally:
        root.destroy()


def test_monitor_formats_real_serial_events_for_display() -> None:
    assert format_trace_event(TraceEvent("CALL", "GrblController.status()")) == (
        "PYTHON",
        "调用 GrblController.status()",
    )
    assert format_trace_event(TraceEvent("TX", "$J=G91 G21 X5 F100")) == (
        "TX → GRBL",
        "$J=G91 G21 X5 F100",
    )
    assert format_trace_event(TraceEvent("RX", "ok")) == ("GRBL → RX", "ok")


def test_monitor_buttons_only_expose_bounded_observable_jogs() -> None:
    assert BUTTON_ACTIONS["X 向右 +5 mm"] == ("X", 5.0, 100.0)
    assert BUTTON_ACTIONS["Z 向上 -1 mm"] == ("Z", -1.0, 50.0)
    assert all(abs(distance) <= 5 for _, distance, _ in BUTTON_ACTIONS.values())


def test_monitor_rejects_xy_button_move_outside_p0_workspace() -> None:
    with pytest.raises(ValueError, match="X target"):
        validate_monitor_motion("<Idle|MPos:190.000,0.000,0.000>", "X", 5.0)

    validate_monitor_motion("<Idle|MPos:185.000,0.000,0.000>", "X", 5.0)


@pytest.mark.parametrize(
    ("event", "stage", "explanation"),
    [
        (TraceEvent("CALL", "GrblController.jog(axis=X, distance_mm=5)"), "python", "Python 正在调用持久控制器"),
        (TraceEvent("TX", "$J=G91 G21 X5 F100"), "command", "Python 已把运动指令写入串口"),
        (TraceEvent("RX", "ok"), "accepted", "GRBL 已接收指令；这不等于运动完成"),
        (TraceEvent("TX", "?"), "poll", "Python 正在询问 GRBL 当前状态"),
        (TraceEvent("RX", "<Idle|MPos:5.000,0.000,0.000>"), "complete", "GRBL 报告 Idle，控制周期已完成"),
    ],
)
def test_trace_events_map_to_teacher_facing_causal_stages(
    event: TraceEvent, stage: str, explanation: str
) -> None:
    assert event_stage(event) == stage
    assert describe_trace_event(event) == explanation


def test_command_explanation_teaches_relative_jog_tokens() -> None:
    explanation = explain_trace_event(TraceEvent("TX", "$J=G91 G21 X5 F100"))
    assert explanation.stage == "command"
    assert explanation.heading == "Python 发出运动指令"
    assert "相对" in explanation.plain
    assert "G91" in explanation.technical
    assert explanation.code == 'serial.write(b"$J=G91 G21 X5 F100\\n")'


def test_status_explanation_exposes_real_coordinate_and_state() -> None:
    explanation = explain_status("<Idle|MPos:12.500,-3.000,4.000|FS:0,0>")
    assert explanation.state == "Idle"
    assert explanation.position.x == 12.5
    assert "X=12.5" in explanation.plain
    assert "MPos" in explanation.technical


def test_coordinate_history_uses_real_mpos_frames_and_reports_delta() -> None:
    first = record_coordinate_status("<Idle|MPos:0.000,0.000,0.000|FS:0,0>", None)
    assert first.state == "Idle"
    assert first.position.x == 0.0
    assert first.change == "首次状态帧：建立 GRBL 当前 MPos 记录。"

    moved = record_coordinate_status("<Jog|MPos:5.000,-2.500,1.000|FS:100,0>", first.position)
    assert moved.state == "Jog"
    assert moved.position.y == -2.5
    assert moved.change == "相对上一帧：X +5.000 mm；Y -2.500 mm；Z +1.000 mm。"


def test_protocol_guide_covers_serial_grbl_and_status_line_basics() -> None:
    entries = protocol_guide()
    terms = {entry.term for entry in entries}
    assert {"串口", "COMx", "CH340", "GRBL", "STEP/DIR", "TX", "RX", "MPos", "ok"}.issubset(terms)
    assert all(entry.summary and entry.detail for entry in entries)
    grbl = next(entry for entry in entries if entry.term == "GRBL")
    assert "Arduino" in grbl.detail
    assert "步进脉冲" in grbl.detail
    assert "编码器" in grbl.detail
    serial = next(entry for entry in entries if entry.term == "串口")
    assert "Windows" in serial.detail
    assert "COMx" in serial.detail
    assert "CH340" in serial.detail
    comx = next(entry for entry in entries if entry.term == "COMx")
    assert "--port COM4" in comx.detail
    ch340 = next(entry for entry in entries if entry.term == "CH340")
    assert "不负责解析 G-code" in ch340.detail


def test_stream_row_keeps_live_log_compact_and_explanation_separate() -> None:
    row = format_stream_row(7, TraceEvent("RX", "ok"))
    assert row[0] == "#07  RX  GRBL → RX"
    assert row[1] == "ok"
    assert row[2] == "GRBL 已接收指令；这不等于运动完成"


def test_status_frame_is_split_into_named_fields_with_verified_meanings() -> None:
    fields = parse_status_fields("<Jog|MPos:0.225,0.000,0.000|FS:100,0|Pn:P>")
    assert [(field.name, field.value) for field in fields] == [
        ("状态", "Jog"),
        ("MPos", "X=0.225 mm，Y=0.000 mm，Z=0.000 mm"),
        ("FS", "进给 100 mm/min；主轴 0 RPM"),
        ("Pn", "P"),
    ]
    assert "运动中" in fields[0].meaning
    assert "探针" in fields[3].meaning


def test_frame_detail_explains_direction_and_each_status_token() -> None:
    detail = format_frame_fields(TraceEvent("RX", "<Jog|MPos:0.225,0.000,0.000|FS:100,0|Pn:P>"))
    assert "RX / Receive" in detail
    assert "State / 机器状态 = Jog" in detail
    assert "MPos / Machine Position" in detail
    assert "FS / Feed rate and Spindle speed" in detail
    assert "Pn / Pin State" in detail
    assert "不能作为完成依据" in detail


def test_frame_detail_expands_tx_transmit_and_rx_receive() -> None:
    tx_detail = format_frame_fields(TraceEvent("TX", "$J=G91 G21 X5 F100"))
    ok_detail = format_frame_fields(TraceEvent("RX", "ok"))
    assert "TX / Transmit" in tx_detail
    assert "电脑 → GRBL" in tx_detail
    assert "RX / Receive" in ok_detail
    assert "GRBL → 电脑" in ok_detail
