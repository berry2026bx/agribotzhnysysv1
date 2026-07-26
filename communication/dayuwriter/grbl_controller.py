from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite
from typing import Any

import serial

from .grbl_protocol import JogCommand, LineKind, encode_jog, parse_line, validate_jog


@dataclass(frozen=True)
class GrblStatus:
    raw: str
    state: str


@dataclass(frozen=True)
class JogResult:
    command: JogCommand
    acceptance: str
    final_status: GrblStatus


class ControllerError(RuntimeError):
    pass


class GrblController:
    def __init__(
        self,
        port: str,
        *,
        baudrate: int = 115200,
        read_timeout_s: float = 0.2,
        write_timeout_s: float = 1.0,
        startup_delay_s: float = 2.0,
        response_deadline_s: float = 5.0,
        completion_deadline_s: float = 15.0,
        poll_interval_s: float = 0.1,
        serial_factory: Callable[..., Any] = serial.Serial,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.read_timeout_s = _validate_duration("read_timeout_s", read_timeout_s)
        self.write_timeout_s = _validate_duration("write_timeout_s", write_timeout_s)
        self.startup_delay_s = _validate_duration(
            "startup_delay_s", startup_delay_s, allow_zero=True
        )
        self.response_deadline_s = _validate_duration(
            "response_deadline_s", response_deadline_s
        )
        self.completion_deadline_s = _validate_duration(
            "completion_deadline_s", completion_deadline_s
        )
        self.poll_interval_s = _validate_duration("poll_interval_s", poll_interval_s)
        self._serial_factory = serial_factory
        self._clock = clock
        self._sleeper = sleeper
        self._serial: Any | None = None

    def open(self) -> None:
        if self._serial is not None:
            return
        try:
            self._serial = self._serial_factory(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.read_timeout_s,
                write_timeout=self.write_timeout_s,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
            if self.startup_delay_s > 0:
                self._sleeper(self.startup_delay_s)
            self._serial.reset_input_buffer()
        except Exception as exc:
            serial_port = self._serial
            self._serial = None
            if serial_port is not None:
                try:
                    serial_port.close()
                except Exception:
                    pass
            raise ControllerError(f"failed to open GRBL port {self.port!r}") from exc

    def close(self) -> None:
        serial_port = self._serial
        if serial_port is None:
            return
        try:
            serial_port.close()
        except Exception as exc:
            raise ControllerError(f"failed to close GRBL port {self.port!r}") from exc
        self._serial = None

    def __enter__(self) -> GrblController:
        self.open()
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> bool:
        if exc_type is None:
            self.close()
        else:
            try:
                self.close()
            except ControllerError as close_error:
                if hasattr(exc_value, "add_note"):
                    exc_value.add_note(f"GRBL controller close failed: {close_error}")
        return False

    def status(self) -> GrblStatus:
        return self._status_until(
            self._clock() + self.response_deadline_s,
            "timeout waiting for GRBL status",
        )

    def _status_until(self, deadline: float, timeout_message: str) -> GrblStatus:
        serial_port = self._require_open()
        if self._clock() >= deadline:
            raise ControllerError(timeout_message)
        self._write(serial_port, b"?")
        while self._clock() < deadline:
            parsed = self._read_parsed_until(serial_port, deadline)
            if parsed is None:
                self._sleep_until(deadline)
                continue
            if parsed.kind is LineKind.STATUS:
                fields = parsed.raw[1:-1].split("|")
                state = fields[0] if fields else ""
                return GrblStatus(raw=parsed.raw, state=state)
            if parsed.kind is LineKind.ERROR:
                raise ControllerError(f"GRBL status error: {parsed.raw}")
            if parsed.kind is LineKind.ALARM:
                raise ControllerError(f"GRBL alarm while reading status: {parsed.raw}")
        raise ControllerError(timeout_message)

    def jog(self, command: JogCommand) -> JogResult:
        normalized = validate_jog(command)
        before = self.status()
        if before.state != "Idle":
            raise ControllerError(f"jog requires Idle state, got {before.state!r}")

        serial_port = self._require_open()
        self._write(serial_port, encode_jog(normalized))
        acceptance = self._wait_for_acceptance(serial_port)

        deadline = self._clock() + self.completion_deadline_s
        while self._clock() < deadline:
            final_status = self._status_until(
                deadline,
                "timeout waiting for GRBL jog completion",
            )
            if final_status.state == "Idle":
                return JogResult(command=normalized, acceptance=acceptance, final_status=final_status)
            self._sleep_until(deadline)
        raise ControllerError("timeout waiting for GRBL jog completion")

    def _require_open(self) -> Any:
        if self._serial is None:
            raise ControllerError("GRBL controller is not open")
        return self._serial

    def _write(self, serial_port: Any, payload: bytes) -> None:
        try:
            serial_port.write(payload)
        except Exception as exc:
            raise ControllerError("serial write failed") from exc

    def _read_parsed_until(self, serial_port: Any, deadline: float):
        remaining = deadline - self._clock()
        if remaining <= 0:
            return None
        try:
            serial_port.timeout = min(self.read_timeout_s, remaining)
            try:
                raw = serial_port.readline()
            finally:
                serial_port.timeout = self.read_timeout_s
        except Exception as exc:
            raise ControllerError("serial read failed") from exc
        if not raw:
            return None
        if isinstance(raw, bytes):
            text = raw.decode("ascii", errors="replace")
        else:
            text = str(raw)
        return parse_line(text)

    def _wait_for_acceptance(self, serial_port: Any) -> str:
        deadline = self._clock() + self.response_deadline_s
        while self._clock() < deadline:
            parsed = self._read_parsed_until(serial_port, deadline)
            if parsed is None:
                self._sleep_until(deadline)
                continue
            if parsed.kind is LineKind.ACK:
                return parsed.raw
            if parsed.kind is LineKind.ERROR:
                raise ControllerError(f"GRBL jog rejected: {parsed.raw}")
            if parsed.kind is LineKind.ALARM:
                raise ControllerError(f"GRBL alarm during jog: {parsed.raw}")
        raise ControllerError("timeout waiting for GRBL jog acceptance (ok)")

    def _sleep_until(self, deadline: float) -> None:
        remaining = deadline - self._clock()
        if remaining > 0:
            self._sleeper(min(self.poll_interval_s, remaining))


def _validate_duration(name: str, value: object, *, allow_zero: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        duration = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not isfinite(duration) or duration < 0 or (duration == 0 and not allow_zero):
        qualifier = "non-negative" if allow_zero else "greater than zero"
        raise ValueError(f"{name} must be finite and {qualifier}")
    return duration
