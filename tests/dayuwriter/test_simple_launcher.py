import sys

import pytest

from communication.dayuwriter.simple_launcher import (
    LauncherError,
    build_calibration_jog,
    build_follow_command,
    parse_p0_baseline,
)
from communication.dayuwriter.grbl_protocol import JogCommand


def test_parse_p0_baseline_accepts_only_a_ready_current_red_target() -> None:
    baseline = parse_p0_baseline(
        {
            "state": "ready",
            "mapping_state": "available",
            "motion_permission": "display_only",
            "target": {"center_uv": {"u": 100, "v": 200}},
            "machine_xy_mm": {"x": 1.927, "y": 0.169},
        }
    )

    assert baseline == pytest.approx((1.927, 0.169))


def test_parse_p0_baseline_rejects_cached_or_incomplete_display_state() -> None:
    with pytest.raises(LauncherError, match="ready"):
        parse_p0_baseline(
            {
                "state": "ready",
                "mapping_state": "unavailable",
                "motion_permission": "display_only",
                "target": {"center_uv": {"u": 100, "v": 200}},
            }
        )


def test_auto_follow_command_waits_for_a_changed_target_and_keeps_z_suspended() -> None:
    command = build_follow_command(
        python=sys.executable,
        port="COM4",
        baseline=(1.927, 0.169),
        dashboard_url="http://127.0.0.1:8765/state.json",
    )

    assert command[:3] == [sys.executable, "-m", "communication.dayuwriter.visual_follow"]
    assert "--continuous" in command
    assert "--wait-for-target-change" in command
    assert "--until-stopped" in command
    assert "--return-to-p0" in command
    assert "--hold-at-target-seconds" in command
    assert command[command.index("--hold-at-target-seconds") + 1] == "10"
    assert "--execute" in command
    assert "--physical-preflight" in command
    assert "--z-drop-mm" not in command


def test_calibration_jogs_are_limited_to_the_four_explicit_30_mm_xy_checks() -> None:
    assert build_calibration_jog("X+30") == (JogCommand("X", 5.0, 100.0),) * 6
    assert build_calibration_jog("X-30") == (JogCommand("X", -5.0, 100.0),) * 6
    assert build_calibration_jog("Y+30") == (JogCommand("Y", 5.0, 100.0),) * 6
    assert build_calibration_jog("Y-30") == (JogCommand("Y", -5.0, 100.0),) * 6

    with pytest.raises(LauncherError, match="unsupported"):
        build_calibration_jog("Z+1")
