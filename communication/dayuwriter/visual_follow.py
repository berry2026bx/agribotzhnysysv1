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
MAX_INITIAL_DEMO_DELTA_MM = 30.0
MAX_Z_DROP_MM = 1.0


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
    if abs(delta_x_mm) > MAX_INITIAL_DEMO_DELTA_MM or abs(delta_y_mm) > MAX_INITIAL_DEMO_DELTA_MM:
        raise VisualFollowError(
            f"initial visual target must be within +/-{MAX_INITIAL_DEMO_DELTA_MM:g} mm per axis"
        )

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
    parser.add_argument("--feed", type=float, default=50.0, help="XY feed in mm/min, maximum 100")
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
    return parser


def run(
    args: Any,
    *,
    fetcher: Callable[[str], Mapping[str, Any]] = fetch_dashboard_state,
    controller_factory: Callable[[str], GrblController] = GrblController,
) -> int:
    """Print the visual proposal; serial is opened only for explicit execution."""

    try:
        target = fetch_ready_live_target(args.dashboard_url, fetcher=fetcher)
        baseline = FollowBaseline(args.baseline_x, args.baseline_y)
        z_drop_mm = getattr(args, "z_drop_mm", 0.0)
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
