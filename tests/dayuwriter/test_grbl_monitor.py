from communication.dayuwriter.grbl_controller import TraceEvent
import pytest

from communication.dayuwriter.grbl_monitor import (
    BUTTON_ACTIONS,
    format_trace_event,
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
