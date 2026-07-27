from communication.dayuwriter.grbl_controller import TraceEvent
import pytest

from communication.dayuwriter.grbl_monitor import (
    BUTTON_ACTIONS,
    describe_trace_event,
    explain_status,
    explain_trace_event,
    event_stage,
    format_trace_event,
    protocol_guide,
    validate_monitor_motion,
)


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


def test_protocol_guide_covers_serial_grbl_and_status_line_basics() -> None:
    entries = protocol_guide()
    terms = {entry.term for entry in entries}
    assert {"串口", "GRBL", "TX", "RX", "MPos", "ok"}.issubset(terms)
    assert all(entry.summary and entry.detail for entry in entries)
