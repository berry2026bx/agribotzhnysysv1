from collections import deque

import pytest

from communication.dayuwriter.grbl_diag import (
    DiagnosticError,
    collect_diagnostics,
    collect_query,
)


class TickClock:
    def __init__(self, step: float = 0.25) -> None:
        self.value = 0.0
        self.step = step

    def __call__(self) -> float:
        self.value += self.step
        return self.value


class FakeSerial:
    def __init__(self, startup=(), responses=None) -> None:
        self.lines = deque(line.encode("ascii") + b"\r\n" for line in startup)
        self.responses = responses or {}
        self.writes = []

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        for line in self.responses.get(data, ()):
            self.lines.append(line.encode("ascii") + b"\r\n")
        return len(data)

    def readline(self) -> bytes:
        return self.lines.popleft() if self.lines else b""


def test_collect_diagnostics_sends_only_read_only_commands() -> None:
    fake = FakeSerial(
        startup=("Grbl 1.1f kvenjoy.com ['$' for help]",),
        responses={
            b"$I\n": ("[VER:1.1f.20170801:]", "ok"),
            b"$$\n": ("$100=80.000", "ok"),
            b"$#\n": ("[G54:0.000,0.000,0.000]", "ok"),
            b"$G\n": ("[GC:G0 G54 G17 G21 G90 G94 M5 M9 T0 F0 S0]", "ok"),
            b"?": ("<Idle|MPos:0.000,0.000,0.000|FS:0,0>",),
        },
    )
    sections = collect_diagnostics(
        fake,
        startup_window_s=0.5,
        query_deadline_s=2.0,
        clock=TickClock(step=0.1),
    )
    assert fake.writes == [b"$I\n", b"$$\n", b"$#\n", b"$G\n", b"?"]
    assert sections["?"][-1].startswith("<Idle|")


def test_collect_query_times_out() -> None:
    with pytest.raises(DiagnosticError, match="timeout"):
        collect_query(FakeSerial(), "$I", 0.5, TickClock(step=0.2))


@pytest.mark.parametrize("line", ["error:20", "ALARM:1"])
def test_collect_query_rejects_error_and_alarm(line: str) -> None:
    fake = FakeSerial(responses={b"$I\n": (line,)})
    with pytest.raises(DiagnosticError, match=line.split(":")[0]):
        collect_query(fake, "$I", 1.0, TickClock(step=0.1))

