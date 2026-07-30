"""Bounded conversion from a live visual target to relative XY jogs."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from math import isfinite
from collections.abc import Callable, Sequence
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from .grbl_controller import ControllerError, GrblController
from .grbl_protocol import (
    MAX_Z_FEED_MM_MIN,
    MIN_JOG_DISTANCE_MM,
    JogCommand,
    encode_jog,
    validate_jog,
)
from .workspace import split_delta


MIN_FOLLOW_DELTA_MM = 1.0
MAX_P0_FOLLOW_OFFSET_MM = 60.0
MAX_Z_DROP_MM = 1.0
REQUIRED_STABLE_TARGET_SAMPLES = 3
MAX_STABLE_TARGET_SPREAD_MM = 1.0


class VisualFollowError(ValueError):
    """Raised when live visual data cannot produce a safe XY proposal."""


@dataclass(frozen=True)
class FollowBaseline:
    """Visual machine-XY reading observed while the pen is physically at P0."""

    x_mm: float
    y_mm: float


@dataclass(frozen=True)
class LiveTarget:
    """One valid display-only dashboard target expressed in machine XY."""

    x_mm: float
    y_mm: float


@dataclass(frozen=True)
class FollowProposal:
    """A bounded XY delta and the corresponding GRBL relative jogs."""

    delta_x_mm: float
    delta_y_mm: float
    commands: tuple[JogCommand, ...]


class ContinuousFollowSession:
    """Build XY corrections from the last successfully commanded target."""

    def __init__(self, p0_baseline: FollowBaseline, *, feed_mm_min: float = 50.0) -> None:
        _validate_point("P0 baseline", p0_baseline.x_mm, p0_baseline.y_mm)
        self._p0_baseline = p0_baseline
        self._commanded_position = p0_baseline
        self._recent_targets: list[LiveTarget] = []
        self._last_returned_target: LiveTarget | None = None
        self._feed_mm_min = feed_mm_min

    def observe(self, target: LiveTarget) -> tuple[LiveTarget, FollowProposal] | None:
        """Return a proposal only after three tight, ready target samples."""

        _validate_point("target", target.x_mm, target.y_mm)
        if self._last_returned_target is not None and not _target_changed(
            self._last_returned_target, target
        ):
            self._recent_targets.clear()
            return None
        self._recent_targets.append(target)
        if len(self._recent_targets) > REQUIRED_STABLE_TARGET_SAMPLES:
            self._recent_targets.pop(0)
        if len(self._recent_targets) < REQUIRED_STABLE_TARGET_SAMPLES:
            return None
        if not _targets_are_stable(self._recent_targets):
            return None
        stable_target = _mean_target(self._recent_targets)
        _validate_target_within_p0_envelope(self._p0_baseline, stable_target)
        proposal = build_target_move_proposal(
            self._commanded_position,
            stable_target,
            feed_mm_min=self._feed_mm_min,
        )
        if not proposal.commands:
            return None
        return stable_target, proposal

    def mark_executed(self, target: LiveTarget, proposal: FollowProposal) -> None:
        """Advance only axes that the controller actually jogged."""

        moved_axes = {command.axis for command in proposal.commands}
        self._commanded_position = FollowBaseline(
            target.x_mm if "X" in moved_axes else self._commanded_position.x_mm,
            target.y_mm if "Y" in moved_axes else self._commanded_position.y_mm,
        )

    def mark_returned_to_p0(self, completed_target: LiveTarget) -> None:
        """Arm the next cycle only after the target has visibly changed."""

        self._commanded_position = self._p0_baseline
        self._recent_targets.clear()
        self._last_returned_target = completed_target

    @property
    def commanded_position(self) -> FollowBaseline:
        """The estimated XY position after successful controller completions."""

        return self._commanded_position


def _targets_are_stable(targets: Sequence[LiveTarget]) -> bool:
    return (
        max(target.x_mm for target in targets) - min(target.x_mm for target in targets)
        <= MAX_STABLE_TARGET_SPREAD_MM
        and max(target.y_mm for target in targets) - min(target.y_mm for target in targets)
        <= MAX_STABLE_TARGET_SPREAD_MM
    )


def _target_changed(previous: LiveTarget, current: LiveTarget) -> bool:
    return (
        abs(current.x_mm - previous.x_mm) >= MIN_FOLLOW_DELTA_MM
        or abs(current.y_mm - previous.y_mm) >= MIN_FOLLOW_DELTA_MM
    )


def _mean_target(targets: Sequence[LiveTarget]) -> LiveTarget:
    count = len(targets)
    return LiveTarget(
        sum(target.x_mm for target in targets) / count,
        sum(target.y_mm for target in targets) / count,
    )


def _validate_target_within_p0_envelope(
    p0_baseline: FollowBaseline,
    target: LiveTarget,
) -> None:
    delta_x_mm = target.x_mm - p0_baseline.x_mm
    delta_y_mm = target.y_mm - p0_baseline.y_mm
    if abs(delta_x_mm) > MAX_P0_FOLLOW_OFFSET_MM or abs(delta_y_mm) > MAX_P0_FOLLOW_OFFSET_MM:
        raise VisualFollowError(
            f"visual target must be within +/-{MAX_P0_FOLLOW_OFFSET_MM:g} mm of P0 per axis"
        )


def parse_live_target(payload: Mapping[str, Any]) -> LiveTarget:
    """Accept only a ready, display-only dashboard snapshot with an XY target."""

    if payload.get("state") != "ready":
        raise VisualFollowError("dashboard state must be ready")
    if payload.get("mapping_state") != "available":
        raise VisualFollowError("dashboard mapping_state must be available")
    if payload.get("motion_permission") != "display_only":
        raise VisualFollowError("dashboard must explicitly be display_only")
    if not isinstance(payload.get("target"), Mapping):
        raise VisualFollowError("dashboard has no detected red target")
    machine_xy = payload.get("machine_xy_mm")
    if not isinstance(machine_xy, Mapping):
        raise VisualFollowError("dashboard has no machine_xy_mm target")
    try:
        x_mm = float(machine_xy["x"])
        y_mm = float(machine_xy["y"])
    except (KeyError, TypeError, ValueError) as exc:
        raise VisualFollowError("dashboard machine_xy_mm must contain finite x and y") from exc
    if not isfinite(x_mm) or not isfinite(y_mm):
        raise VisualFollowError("dashboard machine_xy_mm must contain finite x and y")
    return LiveTarget(x_mm=x_mm, y_mm=y_mm)


def build_follow_proposal(
    baseline: FollowBaseline,
    target: LiveTarget,
    *,
    feed_mm_min: float = 50.0,
) -> FollowProposal:
    """Build a no-Z target proposal from target-minus-P0-baseline."""

    return build_target_move_proposal(baseline, target, feed_mm_min=feed_mm_min)


def build_target_move_proposal(
    baseline: FollowBaseline,
    target: LiveTarget,
    *,
    feed_mm_min: float = 50.0,
    z_drop_mm: float = 0.0,
) -> FollowProposal:
    """Build a bounded X/Y target path followed by an optional downward Z+ jog."""

    _validate_point("baseline", baseline.x_mm, baseline.y_mm)
    _validate_point("target", target.x_mm, target.y_mm)
    delta_x_mm = target.x_mm - baseline.x_mm
    delta_y_mm = target.y_mm - baseline.y_mm
    _validate_target_within_p0_envelope(baseline, target)

    try:
        z_drop_mm = float(z_drop_mm)
    except (TypeError, ValueError) as exc:
        raise VisualFollowError("Z drop must be a finite value between 0 and 1 mm") from exc
    if not isfinite(z_drop_mm) or not 0.0 <= z_drop_mm <= MAX_Z_DROP_MM:
        raise VisualFollowError(
            f"Z drop must be within [0, {MAX_Z_DROP_MM:g}] mm"
        )

    commands: list[JogCommand] = []
    for axis, distance_mm in (("X", delta_x_mm), ("Y", delta_y_mm)):
        if abs(distance_mm) >= MIN_FOLLOW_DELTA_MM:
            commands.extend(
                validate_jog(JogCommand(axis, segment_mm, feed_mm_min))
                for segment_mm in split_delta(distance_mm)
            )
    if z_drop_mm >= MIN_JOG_DISTANCE_MM:
        commands.append(validate_jog(JogCommand("Z", z_drop_mm, MAX_Z_FEED_MM_MIN)))
    return FollowProposal(delta_x_mm, delta_y_mm, tuple(commands))


def fetch_dashboard_state(url: str) -> Mapping[str, Any]:
    """Read one JSON snapshot from the display-only dashboard."""

    try:
        with urlopen(url, timeout=3.0) as response:  # noqa: S310 - caller chooses loopback URL.
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VisualFollowError(f"cannot read dashboard state: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise VisualFollowError("dashboard response must be a JSON object")
    return payload


def fetch_ready_live_target(
    url: str,
    *,
    fetcher: Callable[[str], Mapping[str, Any]] = fetch_dashboard_state,
    attempts: int = 10,
    sleeper: Callable[[float], None] = time.sleep,
) -> LiveTarget:
    """Wait briefly for a complete ready frame, without accepting degraded data."""

    if attempts < 1:
        raise ValueError("attempts must be at least one")
    last_error: VisualFollowError | None = None
    for attempt in range(attempts):
        try:
            return parse_live_target(fetcher(url))
        except VisualFollowError as exc:
            last_error = exc
            if attempt + 1 < attempts:
                sleeper(0.1)
    raise VisualFollowError(f"no ready visual target after {attempts} attempts: {last_error}")


def execute_follow(
    port: str,
    proposal: FollowProposal,
    controller_factory: Callable[[str], GrblController] = GrblController,
) -> tuple[Any, ...]:
    """Execute the already-validated X/Y commands through one serial session."""

    if not proposal.commands:
        raise VisualFollowError("target is already at the visual P0 baseline")
    with controller_factory(port) as controller:
        return tuple(controller.jog(command) for command in proposal.commands)


def execute_continuous_follow(
    port: str,
    p0_baseline: FollowBaseline,
    *,
    max_moves: int,
    max_observations: int,
    return_to_p0: bool = False,
    hold_at_target_s: float = 0.0,
    wait_for_target_change: bool = False,
    dashboard_url: str = "http://127.0.0.1:8765/state.json",
    feed_mm_min: float = 50.0,
    fetcher: Callable[[str], Mapping[str, Any]] = fetch_dashboard_state,
    controller_factory: Callable[[str], GrblController] = GrblController,
    sleeper: Callable[[float], None] = time.sleep,
) -> tuple[Any, ...]:
    """Follow stable target changes for a finite, explicitly bounded session."""

    if not 1 <= max_moves <= 10:
        raise VisualFollowError("continuous follow max_moves must be within [1, 10]")
    if not 3 <= max_observations <= 240:
        raise VisualFollowError("continuous follow max_observations must be within [3, 240]")
    try:
        hold_at_target_s = float(hold_at_target_s)
    except (TypeError, ValueError) as exc:
        raise VisualFollowError("hold_at_target_s must be within [0, 10]") from exc
    if not isfinite(hold_at_target_s) or not 0.0 <= hold_at_target_s <= 10.0:
        raise VisualFollowError("hold_at_target_s must be within [0, 10]")
    if hold_at_target_s > 0.0 and not return_to_p0:
        raise VisualFollowError("hold_at_target_s requires return_to_p0")
    session = ContinuousFollowSession(p0_baseline, feed_mm_min=feed_mm_min)
    if wait_for_target_change:
        session.mark_returned_to_p0(
            fetch_ready_live_target(
                dashboard_url,
                fetcher=fetcher,
                attempts=3,
                sleeper=sleeper,
            )
        )
    results: list[Any] = []
    completed_moves = 0
    with controller_factory(port) as controller:
        for observation_index in range(max_observations):
            target = fetch_ready_live_target(
                dashboard_url,
                fetcher=fetcher,
                attempts=3,
                sleeper=sleeper,
            )
            candidate = session.observe(target)
            if candidate is not None:
                stable_target, proposal = candidate
                for command in proposal.commands:
                    results.append(controller.jog(command))
                session.mark_executed(stable_target, proposal)
                completed_moves += 1
                if return_to_p0:
                    if hold_at_target_s > 0.0:
                        sleeper(hold_at_target_s)
                    return_target = LiveTarget(p0_baseline.x_mm, p0_baseline.y_mm)
                    return_proposal = build_target_move_proposal(
                        session.commanded_position,
                        return_target,
                        feed_mm_min=feed_mm_min,
                    )
                    for command in return_proposal.commands:
                        results.append(controller.jog(command))
                    session.mark_returned_to_p0(stable_target)
                if completed_moves >= max_moves:
                    break
            if observation_index + 1 < max_observations:
                sleeper(0.25)
    return tuple(results)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preview or explicitly execute a bounded red-target XY follow proposal."
    )
    parser.add_argument(
        "--dashboard-url",
        default="http://127.0.0.1:8765/state.json",
        help="Display-only dashboard state endpoint",
    )
    parser.add_argument("--baseline-x", required=True, type=float, help="P0 visual baseline X in mm")
    parser.add_argument("--baseline-y", required=True, type=float, help="P0 visual baseline Y in mm")
    parser.add_argument("--feed", type=float, default=500.0, help="XY feed in mm/min, maximum 500")
    parser.add_argument("--port", help="Live CH340 COM port; required with --execute")
    parser.add_argument("--execute", action="store_true", help="Send the bounded proposal to GRBL")
    parser.add_argument(
        "--physical-preflight",
        action="store_true",
        help="Acknowledge pen-at-P0, suspended tip, 12V, and clear XY path",
    )
    parser.add_argument(
        "--z-drop-mm",
        type=float,
        default=0.0,
        help="Optional final downward Z+ jog in mm; maximum 1 mm",
    )
    parser.add_argument(
        "--z-drop-preflight",
        action="store_true",
        help="Acknowledge at least 1 mm clear downward Z space for --z-drop-mm",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Follow stable red-target changes in XY only for a finite session",
    )
    parser.add_argument(
        "--wait-for-target-change",
        action="store_true",
        help="Arm at the current red target and wait until it changes before the first XY cycle",
    )
    parser.add_argument(
        "--max-moves",
        type=int,
        default=1,
        help="Maximum successful XY corrections in continuous mode; default 1, maximum 10",
    )
    parser.add_argument(
        "--max-observations",
        type=int,
        default=120,
        help="Maximum 250 ms target observations in continuous mode; maximum 240",
    )
    return_mode = parser.add_mutually_exclusive_group()
    return_mode.add_argument(
        "--return-to-p0",
        dest="return_to_p0",
        action="store_true",
        help="After a normal continuous session, return XY to the armed P0 position (default)",
    )
    return_mode.add_argument(
        "--stay-at-target",
        dest="return_to_p0",
        action="store_false",
        help="Keep XY at the target after a continuous session",
    )
    parser.set_defaults(return_to_p0=True)
    parser.add_argument(
        "--hold-at-target-seconds",
        type=float,
        default=10.0,
        help="Hold at the final target for 0 to 10 seconds before returning to P0",
    )
    return parser


def run(
    args: Any,
    *,
    fetcher: Callable[[str], Mapping[str, Any]] = fetch_dashboard_state,
    controller_factory: Callable[[str], GrblController] = GrblController,
) -> int:
    """Print the visual proposal; serial is opened only for explicit execution."""

    try:
        baseline = FollowBaseline(args.baseline_x, args.baseline_y)
        z_drop_mm = getattr(args, "z_drop_mm", 0.0)
        if getattr(args, "continuous", False):
            return _run_continuous_follow(
                args,
                baseline,
                z_drop_mm=z_drop_mm,
                fetcher=fetcher,
                controller_factory=controller_factory,
            )
        target = fetch_ready_live_target(args.dashboard_url, fetcher=fetcher)
        proposal = build_target_move_proposal(
            baseline,
            target,
            feed_mm_min=args.feed,
            z_drop_mm=z_drop_mm,
        )
        _print_proposal(target, baseline, proposal)
        if not args.execute:
            print("preview only; no serial port opened")
            return 0
        if not args.physical_preflight:
            raise VisualFollowError("--execute requires --physical-preflight")
        if float(z_drop_mm) > 0.0 and not getattr(args, "z_drop_preflight", False):
            raise VisualFollowError("--z-drop-mm requires --z-drop-preflight")
        if not args.port:
            raise VisualFollowError("--execute requires --port COMx")
        results = execute_follow(args.port, proposal, controller_factory)
    except (VisualFollowError, ControllerError, OSError, ValueError) as exc:
        print(f"Visual follow failed: {exc}", file=sys.stderr)
        return 2
    for result in results:
        print(f"accepted: {result.acceptance}")
        print(f"final: {result.final_status.raw}")
    return 0


def _run_continuous_follow(
    args: Any,
    baseline: FollowBaseline,
    *,
    z_drop_mm: float,
    fetcher: Callable[[str], Mapping[str, Any]],
    controller_factory: Callable[[str], GrblController],
) -> int:
    if float(z_drop_mm) != 0.0:
        raise VisualFollowError("continuous follow keeps Z suspended; --z-drop-mm must be 0")
    if not args.execute:
        raise VisualFollowError("continuous follow requires --execute")
    if not args.physical_preflight:
        raise VisualFollowError("continuous follow requires --physical-preflight")
    if not args.port:
        raise VisualFollowError("continuous follow requires --port COMx")
    results = execute_continuous_follow(
        args.port,
        baseline,
        max_moves=getattr(args, "max_moves", 1),
        max_observations=getattr(args, "max_observations", 120),
        dashboard_url=args.dashboard_url,
        feed_mm_min=args.feed,
        return_to_p0=getattr(args, "return_to_p0", True),
        hold_at_target_s=getattr(args, "hold_at_target_seconds", 10.0),
        wait_for_target_change=getattr(args, "wait_for_target_change", False),
        fetcher=fetcher,
        controller_factory=controller_factory,
    )
    if not results:
        print("continuous follow ended without a stable target correction")
        return 0
    for result in results:
        print(f"accepted: {result.acceptance}")
        print(f"final: {result.final_status.raw}")
    return 0


def _print_proposal(target: LiveTarget, baseline: FollowBaseline, proposal: FollowProposal) -> None:
    print(f"visual target: X={target.x_mm:.3f} mm, Y={target.y_mm:.3f} mm")
    print(f"P0 visual baseline: X={baseline.x_mm:.3f} mm, Y={baseline.y_mm:.3f} mm")
    print(f"proposed delta: X={proposal.delta_x_mm:.3f} mm, Y={proposal.delta_y_mm:.3f} mm")
    if proposal.commands:
        for command in proposal.commands:
            print(f"proposed GRBL: {encode_jog(command).decode('ascii').strip()}")
    else:
        print("proposed GRBL: none")


def main(argv: Sequence[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


def _validate_point(name: str, x_mm: float, y_mm: float) -> None:
    if not isfinite(x_mm) or not isfinite(y_mm):
        raise VisualFollowError(f"{name} coordinates must be finite")


if __name__ == "__main__":
    raise SystemExit(main())
