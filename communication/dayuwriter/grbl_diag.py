import argparse
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import serial

from .grbl_protocol import LineKind, encode_read_only, parse_line


class SerialLike(Protocol):
    def write(self, data: bytes) -> int: ...
    def readline(self) -> bytes: ...


class DiagnosticError(RuntimeError):
    pass


def read_startup(
    port: SerialLike,
    duration_s: float,
    clock: Callable[[], float] = time.monotonic,
) -> list[str]:
    deadline = clock() + duration_s
    lines: list[str] = []
    while clock() < deadline:
        raw = port.readline()
        if raw:
            lines.append(raw.decode("ascii", errors="replace").strip())
    return lines


def collect_query(
    port: SerialLike,
    command: str,
    deadline_s: float,
    clock: Callable[[], float] = time.monotonic,
) -> list[str]:
    port.write(encode_read_only(command))
    deadline = clock() + deadline_s
    lines: list[str] = []
    while clock() < deadline:
        raw = port.readline()
        if not raw:
            continue
        text = raw.decode("ascii", errors="replace").strip()
        parsed = parse_line(text)
        lines.append(parsed.raw)
        if parsed.kind is LineKind.ERROR:
            raise DiagnosticError(f"error response for {command}: {parsed.raw}")
        if parsed.kind is LineKind.ALARM:
            raise DiagnosticError(f"ALARM response for {command}: {parsed.raw}")
        if command == "?" and parsed.kind is LineKind.STATUS:
            return lines
        if command != "?" and parsed.kind is LineKind.ACK:
            return lines
    raise DiagnosticError(f"timeout waiting for response to {command}")


def collect_diagnostics(
    port: SerialLike,
    startup_window_s: float = 3.0,
    query_deadline_s: float = 5.0,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, list[str]]:
    sections = {"startup": read_startup(port, startup_window_s, clock)}
    for command in ("$I", "$$", "$#", "$G", "?"):
        sections[command] = collect_query(port, command, query_deadline_s, clock)
    return sections


def render_capture(sections: dict[str, list[str]]) -> str:
    output: list[str] = []
    for name, lines in sections.items():
        output.append(f"## {name}")
        output.extend(lines or ["(no lines observed)"])
        output.append("")
    return "\n".join(output)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only GRBL baseline capture")
    parser.add_argument("--port", required=True, help="Live-discovered Windows COM port")
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        with serial.Serial(
            port=args.port,
            baudrate=115200,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.2,
            write_timeout=1.0,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        ) as port:
            sections = collect_diagnostics(port)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render_capture(sections), encoding="utf-8")
        print(f"Read-only capture written to {args.output}")
        return 0
    except (serial.SerialException, DiagnosticError, OSError) as exc:
        print(f"Diagnostic failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

