from argparse import Namespace

import pytest

from communication.dayuwriter.grbl_protocol import JogCommand
from communication.dayuwriter import visual_follow
from communication.dayuwriter.visual_follow import (
    FollowBaseline,
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


def args(**overrides) -> Namespace:
    values = {
        "dashboard_url": "http://127.0.0.1:8765/state.json",
        "baseline_x": 1.9,
        "baseline_y": 0.2,
        "feed": 50.0,
        "port": None,
        "execute": False,
        "physical_preflight": False,
    }
    values.update(overrides)
    return Namespace(**values)


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
