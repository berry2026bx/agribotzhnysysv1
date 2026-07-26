from __future__ import annotations

import argparse
import shlex
from collections.abc import Callable

import serial

from .grbl_controller import ControllerError, GrblController
from .grbl_protocol import JogCommand


HELP_TEXT = """Commands:
  status
  jog <X|Y|Z> <distance_mm> <feed_mm_min>
  help
  quit

Limits: distance 0.001-5 mm; XY feed <= 100; Z feed <= 50.
Current machine convention: positive Z moves downward.
"""


def run_console(
    port: str,
    *,
    controller_factory=GrblController,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> int:
    try:
        with controller_factory(port) as controller:
            status = controller.status()
            output_fn(f"connected: {status.raw}")
            output_fn(HELP_TEXT.rstrip())

            while True:
                try:
                    parts = shlex.split(input_fn("dayuwriter> "))
                except EOFError:
                    output_fn("closed")
                    return 0
                except ValueError as exc:
                    output_fn(f"invalid input: {exc}")
                    continue

                if not parts:
                    continue

                command = parts[0].lower()
                if command in {"quit", "exit"}:
                    output_fn("closed")
                    return 0
                if command == "help":
                    output_fn(HELP_TEXT.rstrip())
                    continue
                if command == "status":
                    if len(parts) != 1:
                        output_fn("usage: status")
                        continue
                    output_fn(f"status: {controller.status().raw}")
                    continue
                if command == "jog":
                    if len(parts) != 4:
                        output_fn("usage: jog <X|Y|Z> <distance_mm> <feed_mm_min>")
                        continue
                    try:
                        jog = JogCommand(parts[1], float(parts[2]), float(parts[3]))
                        result = controller.jog(jog)
                    except ValueError as exc:
                        output_fn(f"invalid jog: {exc}")
                        continue
                    output_fn(f"accepted: {result.acceptance}")
                    output_fn(f"final: {result.final_status.raw}")
                    continue

                output_fn(f"unknown command: {parts[0]!r}; type 'help'")
    except (ControllerError, serial.SerialException, OSError) as exc:
        output_fn(f"controller error: {exc}")
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Interactive bounded DayuWriter control")
    parser.add_argument("--port", required=True, help="Live-discovered Windows COM port")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return run_console(args.port)


if __name__ == "__main__":
    raise SystemExit(main())
