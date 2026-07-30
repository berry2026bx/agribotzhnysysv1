from argparse import Namespace

import pytest

from communication.dayuwriter.grbl_protocol import JogCommand
from communication.dayuwriter import visual_follow
from communication.dayuwriter.visual_follow import (
    FollowBaseline,
    FollowProposal,
    LiveTarget,
    build_follow_proposal,
    execute_follow,
    fetch_ready_live_target,
    parse_live_target,
)


def ready_payload(*, x: float, y: float) -> dict[str, object]:
    return {
        "state": "ready",
        "mapping_state": "available",
        "motion_permission": "display_only",
        "target": {"center_uv": {"u": 620.0, "v": 460.0}},
        "machine_xy_mm": {"x": x, "y": y},
    }


def test_build_follow_proposal_subtracts_the_p0_baseline() -> None:
    target = parse_live_target(ready_payload(x=6.9, y=0.2))

    proposal = build_follow_proposal(FollowBaseline(1.9, 0.2), target)

    assert proposal.delta_x_mm == pytest.approx(5.0)
    assert proposal.delta_y_mm == pytest.approx(0.0)
    assert proposal.commands == (JogCommand("X", 5.0, 50.0),)


def test_build_follow_proposal_ignores_sub_millimetre_visual_jitter() -> None:
    target = parse_live_target(ready_payload(x=2.13, y=-0.02))

    proposal = build_follow_proposal(FollowBaseline(1.93, 0.17), target)

    assert proposal.commands == ()


def test_continuous_session_moves_from_last_commanded_target_without_returning_to_p0() -> None:
    session = visual_follow.ContinuousFollowSession(FollowBaseline(1.927, 0.169))

    assert session.observe(LiveTarget(6.927, 0.169)) is None
    assert session.observe(LiveTarget(6.927, 0.169)) is None
    first = session.observe(LiveTarget(6.927, 0.169))
    assert first is not None
    first_target, first_proposal = first
    assert first_proposal.delta_x_mm == pytest.approx(5.0)
    session.mark_executed(first_target, first_proposal)

    assert session.observe(LiveTarget(10.927, 0.169)) is None
    assert session.observe(LiveTarget(10.927, 0.169)) is None
    second = session.observe(LiveTarget(10.927, 0.169))
    assert second is not None
    _, second_proposal = second
    assert second_proposal.delta_x_mm == pytest.approx(4.0)


def test_build_target_move_proposal_splits_xy_then_appends_z_drop() -> None:
    proposal = visual_follow.build_target_move_proposal(
        FollowBaseline(1.927, 0.169),
        LiveTarget(13.927, 7.169),
        z_drop_mm=1.0,
    )

    assert proposal.delta_x_mm == pytest.approx(12.0)
    assert proposal.delta_y_mm == pytest.approx(7.0)
    assert proposal.commands == (
        JogCommand("X", 4.0, 50.0),
        JogCommand("X", 4.0, 50.0),
        JogCommand("X", 4.0, 50.0),
        JogCommand("Y", 3.5, 50.0),
        JogCommand("Y", 3.5, 50.0),
        JogCommand("Z", 1.0, 50.0),
    )


@pytest.mark.parametrize("target", [LiveTarget(62.0, 0.169), LiveTarget(1.927, -61.0)])
def test_build_target_move_proposal_rejects_target_outside_initial_demo_envelope(
    target: LiveTarget,
) -> None:
    with pytest.raises(visual_follow.VisualFollowError, match="60 mm"):
        visual_follow.build_target_move_proposal(
            FollowBaseline(1.927, 0.169),
            target,
        )


def test_build_target_move_proposal_accepts_target_within_sixty_mm_of_p0() -> None:
    proposal = visual_follow.build_target_move_proposal(
        FollowBaseline(1.927, 0.169),
        LiveTarget(46.927, 0.169),
    )

    assert proposal.delta_x_mm == pytest.approx(45.0)
    assert all(abs(command.distance_mm) <= 5.0 for command in proposal.commands)


def test_build_target_move_proposal_omits_z_when_no_drop_is_requested() -> None:
    proposal = visual_follow.build_target_move_proposal(
        FollowBaseline(1.927, 0.169),
        LiveTarget(6.927, 0.169),
    )

    assert proposal.commands == (JogCommand("X", 5.0, 50.0),)


class FakeController:
    def __init__(self) -> None:
        self.jog_calls: list[JogCommand] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        return False

    def jog(self, command: JogCommand) -> str:
        self.jog_calls.append(command)
        return "done"


def test_execute_follow_uses_one_persistent_controller_for_x_then_y() -> None:
    target = parse_live_target(ready_payload(x=3.9, y=-2.8))
    proposal = build_follow_proposal(FollowBaseline(1.9, 0.2), target)
    controller = FakeController()
    opened_ports: list[str] = []

    def factory(port: str) -> FakeController:
        opened_ports.append(port)
        return controller

    assert execute_follow("COM4", proposal, factory) == ("done", "done")
    assert opened_ports == ["COM4"]
    assert controller.jog_calls == [JogCommand("X", 2.0, 50.0), JogCommand("Y", -3.0, 50.0)]


def test_execute_continuous_follow_keeps_one_controller_for_two_target_changes() -> None:
    controller = FakeController()
    opened_ports: list[str] = []
    snapshots = iter(
        [
            *[ready_payload(x=6.927, y=0.169) for _ in range(3)],
            *[ready_payload(x=10.927, y=0.169) for _ in range(3)],
        ]
    )

    results = visual_follow.execute_continuous_follow(
        "COM4",
        FollowBaseline(1.927, 0.169),
        max_moves=2,
        max_observations=6,
        fetcher=lambda _url: next(snapshots),
        controller_factory=lambda port: (opened_ports.append(port) or controller),
        sleeper=lambda _seconds: None,
    )

    assert len(results) == 2
    assert opened_ports == ["COM4"]
    assert controller.jog_calls == [JogCommand("X", 5.0, 50.0), JogCommand("X", 4.0, 50.0)]


def test_execute_continuous_follow_can_return_to_p0_after_the_session() -> None:
    controller = FakeController()
    snapshots = iter([ready_payload(x=6.927, y=0.169) for _ in range(3)])

    results = visual_follow.execute_continuous_follow(
        "COM4",
        FollowBaseline(1.927, 0.169),
        max_moves=1,
        max_observations=3,
        return_to_p0=True,
        fetcher=lambda _url: next(snapshots),
        controller_factory=lambda _port: controller,
        sleeper=lambda _seconds: None,
    )

    assert len(results) == 2
    assert controller.jog_calls == [JogCommand("X", 5.0, 50.0), JogCommand("X", -5.0, 50.0)]


def test_execute_continuous_follow_holds_ten_seconds_before_returning_to_p0() -> None:
    controller = FakeController()
    snapshots = iter([ready_payload(x=6.927, y=0.169) for _ in range(3)])
    waits: list[float] = []

    visual_follow.execute_continuous_follow(
        "COM4",
        FollowBaseline(1.927, 0.169),
        max_moves=1,
        max_observations=3,
        return_to_p0=True,
        hold_at_target_s=10.0,
        fetcher=lambda _url: next(snapshots),
        controller_factory=lambda _port: controller,
        sleeper=waits.append,
    )

    assert waits[-1] == 10.0
    assert waits.count(10.0) == 1


def test_execute_continuous_follow_returns_to_p0_between_changed_targets() -> None:
    controller = FakeController()
    snapshots = iter(
        [
            *[ready_payload(x=6.927, y=0.169) for _ in range(3)],
            *[ready_payload(x=10.927, y=0.169) for _ in range(3)],
        ]
    )

    results = visual_follow.execute_continuous_follow(
        "COM4",
        FollowBaseline(1.927, 0.169),
        max_moves=2,
        max_observations=6,
        return_to_p0=True,
        fetcher=lambda _url: next(snapshots),
        controller_factory=lambda _port: controller,
        sleeper=lambda _seconds: None,
    )

    assert len(results) == 6
    assert controller.jog_calls == [
        JogCommand("X", 5.0, 50.0),
        JogCommand("X", -5.0, 50.0),
        JogCommand("X", 4.5, 50.0),
        JogCommand("X", 4.5, 50.0),
        JogCommand("X", -4.5, 50.0),
        JogCommand("X", -4.5, 50.0),
    ]


def test_execute_continuous_follow_can_arm_at_current_target_and_wait_for_change() -> None:
    controller = FakeController()
    snapshots = iter(
        [
            ready_payload(x=6.927, y=0.169),
            *[ready_payload(x=6.927, y=0.169) for _ in range(3)],
            *[ready_payload(x=10.927, y=0.169) for _ in range(3)],
        ]
    )

    results = visual_follow.execute_continuous_follow(
        "COM4",
        FollowBaseline(1.927, 0.169),
        max_moves=1,
        max_observations=6,
        return_to_p0=True,
        wait_for_target_change=True,
        fetcher=lambda _url: next(snapshots),
        controller_factory=lambda _port: controller,
        sleeper=lambda _seconds: None,
    )

    assert len(results) == 4
    assert controller.jog_calls == [
        JogCommand("X", 4.5, 50.0),
        JogCommand("X", 4.5, 50.0),
        JogCommand("X", -4.5, 50.0),
        JogCommand("X", -4.5, 50.0),
    ]


def test_execute_continuous_follow_arms_after_a_transient_mapping_outage() -> None:
    controller = FakeController()
    snapshots = iter(
        [
            *[
                {
                    "state": "ready",
                    "mapping_state": "unavailable",
                    "motion_permission": "display_only",
                }
                for _ in range(3)
            ],
            ready_payload(x=6.927, y=0.169),
            *[ready_payload(x=6.927, y=0.169) for _ in range(3)],
            *[ready_payload(x=10.927, y=0.169) for _ in range(3)],
        ]
    )

    results = visual_follow.execute_continuous_follow(
        "COM4",
        FollowBaseline(1.927, 0.169),
        max_moves=1,
        max_observations=8,
        return_to_p0=True,
        wait_for_target_change=True,
        fetcher=lambda _url: next(snapshots),
        controller_factory=lambda _port: controller,
        sleeper=lambda _seconds: None,
    )

    assert len(results) == 4
    assert controller.jog_calls == [
        JogCommand("X", 4.5, 50.0),
        JogCommand("X", 4.5, 50.0),
        JogCommand("X", -4.5, 50.0),
        JogCommand("X", -4.5, 50.0),
    ]


def test_execute_continuous_follow_retries_one_transient_unmapped_frame() -> None:
    controller = FakeController()
    snapshots = iter(
        [
            {"state": "ready", "mapping_state": "unavailable", "motion_permission": "display_only"},
            *[ready_payload(x=6.927, y=0.169) for _ in range(3)],
        ]
    )
    waits: list[float] = []

    results = visual_follow.execute_continuous_follow(
        "COM4",
        FollowBaseline(1.927, 0.169),
        max_moves=1,
        max_observations=3,
        fetcher=lambda _url: next(snapshots),
        controller_factory=lambda _port: controller,
        sleeper=waits.append,
    )

    assert len(results) == 1
    assert controller.jog_calls == [JogCommand("X", 5.0, 50.0)]
    assert waits[0] == 0.1


def test_execute_continuous_follow_allows_a_six_minute_observation_window() -> None:
    controller = FakeController()
    snapshots = iter([ready_payload(x=6.927, y=0.169) for _ in range(3)])

    results = visual_follow.execute_continuous_follow(
        "COM4",
        FollowBaseline(1.927, 0.169),
        max_moves=1,
        max_observations=1440,
        fetcher=lambda _url: next(snapshots),
        controller_factory=lambda _port: controller,
        sleeper=lambda _seconds: None,
    )

    assert len(results) == 1
    assert controller.jog_calls == [JogCommand("X", 5.0, 50.0)]


def args(**overrides) -> Namespace:
    values = {
        "dashboard_url": "http://127.0.0.1:8765/state.json",
        "baseline_x": 1.9,
        "baseline_y": 0.2,
        "feed": 50.0,
        "port": None,
        "execute": False,
        "physical_preflight": False,
        "z_drop_mm": 0.0,
        "z_drop_preflight": False,
        "continuous": False,
        "max_moves": 2,
        "max_observations": 6,
    }
    values.update(overrides)
    return Namespace(**values)


def test_parser_defaults_continuous_demo_to_fast_one_target_return() -> None:
    parsed = visual_follow.build_parser().parse_args(
        ["--baseline-x", "1.0", "--baseline-y", "2.0", "--continuous"]
    )

    assert parsed.feed == 500.0
    assert parsed.max_moves == 1
    assert parsed.return_to_p0 is True
    assert parsed.hold_at_target_seconds == 10.0


def test_parser_can_arm_without_replaying_the_current_red_target() -> None:
    parsed = visual_follow.build_parser().parse_args(
        [
            "--baseline-x",
            "1.0",
            "--baseline-y",
            "2.0",
            "--continuous",
            "--wait-for-target-change",
        ]
    )

    assert parsed.wait_for_target_change is True


def test_preview_does_not_open_a_controller(capsys) -> None:
    factory_calls: list[str] = []

    assert visual_follow.run(
        args(),
        fetcher=lambda _url: ready_payload(x=6.9, y=0.2),
        controller_factory=lambda port: factory_calls.append(port),
    ) == 0

    assert factory_calls == []
    assert "preview only; no serial port opened" in capsys.readouterr().out


def test_execute_requires_the_physical_preflight_acknowledgement(capsys) -> None:
    assert visual_follow.run(
        args(execute=True, port="COM4"),
        fetcher=lambda _url: ready_payload(x=6.9, y=0.2),
    ) == 2

    assert "--physical-preflight" in capsys.readouterr().err


def test_execute_rejects_z_drop_without_separate_z_preflight(capsys) -> None:
    factory_calls: list[str] = []

    assert visual_follow.run(
        args(execute=True, port="COM4", physical_preflight=True, z_drop_mm=1.0),
        fetcher=lambda _url: ready_payload(x=6.927, y=0.169),
        controller_factory=lambda port: factory_calls.append(port),
    ) == 2

    assert factory_calls == []
    assert "--z-drop-preflight" in capsys.readouterr().err


def test_continuous_mode_rejects_z_drop_even_with_z_preflight(capsys) -> None:
    assert visual_follow.run(
        args(
            continuous=True,
            execute=True,
            port="COM4",
            physical_preflight=True,
            z_drop_mm=1.0,
            z_drop_preflight=True,
        ),
        fetcher=lambda _url: ready_payload(x=6.927, y=0.169),
        controller_factory=lambda _port: FakeController(),
    ) == 2

    assert "continuous follow keeps Z suspended" in capsys.readouterr().err


def test_execute_target_move_uses_one_controller_and_runs_z_last() -> None:
    controller = FakeController()
    opened_ports: list[str] = []
    proposal = FollowProposal(
        6.0,
        0.0,
        (JogCommand("X", 3.0, 50.0), JogCommand("X", 3.0, 50.0), JogCommand("Z", 1.0, 50.0)),
    )

    assert execute_follow(
        "COM4",
        proposal,
        lambda port: (opened_ports.append(port) or controller),
    ) == ("done", "done", "done")
    assert opened_ports == ["COM4"]
    assert controller.jog_calls[-1] == JogCommand("Z", 1.0, 50.0)


def test_fetch_ready_live_target_retries_a_transient_depth_failure() -> None:
    snapshots = iter(
        [
            {
                "state": "depth_unavailable",
                "mapping_state": None,
                "motion_permission": "display_only",
            },
            ready_payload(x=6.9, y=0.2),
        ]
    )
    waits: list[float] = []

    target = fetch_ready_live_target(
        "http://127.0.0.1:8765/state.json",
        fetcher=lambda _url: next(snapshots),
        attempts=2,
        sleeper=waits.append,
    )

    assert target.x_mm == pytest.approx(6.9)
    assert target.y_mm == pytest.approx(0.2)
    assert waits == [0.1]
