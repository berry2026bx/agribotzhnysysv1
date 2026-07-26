from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from typing import Any

import serial

from .grbl_controller import ControllerError, GrblController
from .grbl_protocol import JogCommand, validate_jog


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute one bounded GRBL jog")
    parser.add_argument("--port", required=True, help="Live-discovered Windows COM port")
    parser.add_argument("--axis", required=True, choices=("X", "x", "Y", "y", "Z", "z"))
    parser.add_argument("--distance", required=True, type=float, help="Distance in mm")
    parser.add_argument("--feed", required=True, type=float, help="Feed in mm/min")
    return parser


def run(args: Any, controller_factory: Callable[[str], GrblController] = GrblController) -> int:
    command = JogCommand(args.axis, args.distance, args.feed)
    try:
        command = validate_jog(command)
    except (TypeError, ValueError) as exc:
        print(f"Invalid jog: {exc}", file=sys.stderr)
        return 2

    print(
        f"Preflight: port={args.port} axis={command.axis} "
        f"distance_mm={command.distance_mm:g} feed_mm_min={command.feed_mm_min:g}"
    )
    try:
        with controller_factory(args.port) as controller:
            result = controller.jog(command)
        print(f"Final status: {result.final_status.raw}")
        return 0
    except (ControllerError, serial.SerialException, OSError) as exc:
        print(f"Jog failed: {exc}", file=sys.stderr)
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
