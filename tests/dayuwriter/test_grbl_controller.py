from collections import deque

import pytest

from communication.dayuwriter.grbl_controller import (
    ControllerError,
    GrblController,
    GrblStatus,
    JogResult,
)
from communication.dayuwriter.grbl_protocol import JogCommand


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, duration: float) -> None:
        self.sleeps.append(duration)
        self.now += duration


class FakeSerial:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.writes: list[bytes] = []
        self.reads: deque[bytes] = deque()
        self.reset_calls = 0
        self.closed = False
        self.on_write = None
        self.fail_close = False

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        if self.on_write:
            self.on_write(data, self)
        return len(data)

    def readline(self) -> bytes:
        return self.reads.popleft() if self.reads else b""

    def reset_input_buffer(self) -> None:
        self.reset_calls += 1
        self.reads.clear()

    def close(self) -> None:
        if self.fail_close:
            raise OSError("close failed")
        self.closed = True


class FakeFactory:
    def __init__(self) -> None:
        self.instances: list[FakeSerial] = []

    def __call__(self, **kwargs) -> FakeSerial:
        port = FakeSerial(**kwargs)
        self.instances.append(port)
        return port


def make_controller(*, factory: FakeFactory | None = None, clock: FakeClock | None = None, **kwargs):
    factory = factory or FakeFactory()
    clock = clock or FakeClock()
    controller = GrblController(
        "COM-test",
        serial_factory=factory,
        clock=clock,
        sleeper=clock.sleep,
        startup_delay_s=kwargs.pop("startup_delay_s", 0.0),
        poll_interval_s=kwargs.pop("poll_interval_s", 0.1),
        **kwargs,
    )
    return controller, factory, clock


def test_import_and_open_never_write_motion_or_any_bytes() -> None:
    controller, factory, clock = make_controller(startup_delay_s=2.0)

    controller.open()

    serial_port = factory.instances[0]
    assert serial_port.writes == []
    assert serial_port.reset_calls == 1
    assert clock.sleeps == [2.0]
    assert serial_port.kwargs["bytesize"] == 8
    assert serial_port.kwargs["parity"] == "N"
    assert serial_port.kwargs["stopbits"] == 1
    assert serial_port.kwargs["timeout"] == 0.2
    assert serial_port.kwargs["write_timeout"] == 1.0
    assert serial_port.kwargs["xonxoff"] is False
    assert serial_port.kwargs["rtscts"] is False
    assert serial_port.kwargs["dsrdtr"] is False


def test_status_writes_realtime_question_and_parses_state() -> None:
    controller, factory, _ = make_controller()
    controller.open()
    factory.instances[0].reads.append(b"<Idle|MPos:0,0,0|FS:0,0>\r\n")

    result = controller.status()

    assert result == GrblStatus(raw="<Idle|MPos:0,0,0|FS:0,0>", state="Idle")
    assert factory.instances[0].writes == [b"?"]


def test_status_times_out_after_one_realtime_query() -> None:
    controller, factory, _ = make_controller(response_deadline_s=0.3)
    controller.open()

    with pytest.raises(ControllerError, match="timeout"):
        controller.status()

    assert factory.instances[0].writes == [b"?"]


def test_jog_requires_idle_before_writing_motion() -> None:
    controller, factory, _ = make_controller()
    controller.open()
    factory.instances[0].reads.append(b"<Run|MPos:0,0,0|FS:0,0>\n")

    with pytest.raises(ControllerError, match="Idle"):
        controller.jog(JogCommand("X", 1, 50))

    assert factory.instances[0].writes == [b"?"]


def test_jog_waits_for_ok_then_idle_and_returns_result() -> None:
    controller, factory, _ = make_controller()
    controller.open()
    serial_port = factory.instances[0]

    def respond(data: bytes, port: FakeSerial) -> None:
        if data == b"?":
            port.reads.append(b"<Idle|MPos:0,0,0|FS:0,0>\n")
        elif data.startswith(b"$J="):
            port.reads.append(b"ok\n")
            port.reads.append(b"<Run|MPos:1,0,0|FS:50,0>\n")
            port.reads.append(b"<Idle|MPos:1,0,0|FS:0,0>\n")

    serial_port.on_write = respond
    result = controller.jog(JogCommand("x", 1, 50))

    assert result == JogResult(
        command=JogCommand("X", 1.0, 50.0),
        acceptance="ok",
        final_status=GrblStatus(raw="<Idle|MPos:1,0,0|FS:0,0>", state="Idle"),
    )
    assert serial_port.writes == [b"?", b"$J=G91 G21 X1 F50\n", b"?", b"?"]


@pytest.mark.parametrize("response", [b"error:15\n", b"ALARM:1\n"])
def test_jog_raises_immediately_for_error_or_alarm(response: bytes) -> None:
    controller, factory, _ = make_controller()
    controller.open()
    serial_port = factory.instances[0]
    serial_port.reads.append(b"<Idle|MPos:0,0,0|FS:0,0>\n")

    def respond(data: bytes, port: FakeSerial) -> None:
        if data.startswith(b"$J="):
            port.reads.append(response)

    serial_port.on_write = respond

    with pytest.raises(ControllerError):
        controller.jog(JogCommand("X", 1, 50))

    assert serial_port.writes == [b"?", b"$J=G91 G21 X1 F50\n"]


def test_jog_acceptance_timeout_does_not_poll_completion() -> None:
    controller, factory, _ = make_controller(response_deadline_s=0.3)
    controller.open()
    serial_port = factory.instances[0]
    serial_port.reads.append(b"<Idle|MPos:0,0,0|FS:0,0>\n")

    with pytest.raises(ControllerError, match="ok"):
        controller.jog(JogCommand("X", 1, 50))

    assert serial_port.writes == [b"?", b"$J=G91 G21 X1 F50\n"]


def test_jog_completion_timeout_does_not_send_follow_up_motion() -> None:
    controller, factory, _ = make_controller(completion_deadline_s=0.3)
    controller.open()
    serial_port = factory.instances[0]

    def respond(data: bytes, port: FakeSerial) -> None:
        if data == b"?":
            if len(port.writes) == 1:
                port.reads.append(b"<Idle|MPos:0,0,0|FS:0,0>\n")
            else:
                port.reads.append(b"<Run|MPos:0.5,0,0|FS:50,0>\n")
        elif data.startswith(b"$J="):
            port.reads.append(b"ok\n")

    serial_port.on_write = respond

    with pytest.raises(ControllerError, match="completion"):
        controller.jog(JogCommand("X", 1, 50))

    assert serial_port.writes[0:2] == [b"?", b"$J=G91 G21 X1 F50\n"]
    assert all(not data.startswith(b"$J=") for data in serial_port.writes[2:])


def test_close_is_idempotent_and_context_closes_on_failure() -> None:
    controller, factory, _ = make_controller()
    controller.open()
    serial_port = factory.instances[0]
    controller.close()
    controller.close()
    assert serial_port.closed is True

    other, other_factory, _ = make_controller()
    other.open()
    other_serial = other_factory.instances[0]
    other_serial.fail_close = True
    with pytest.raises(ControllerError, match="close"):
        with other:
            raise ValueError("body failed")
    assert other_serial.closed is False
    other.close()


def test_context_closes_after_operational_status_timeout() -> None:
    factory = FakeFactory()
    clock = FakeClock()

    with pytest.raises(ControllerError, match="timeout"):
        with GrblController(
            "COM-test",
            serial_factory=factory,
            clock=clock,
            sleeper=clock.sleep,
            startup_delay_s=0.0,
            response_deadline_s=0.3,
        ) as controller:
            controller.status()

    assert factory.instances[0].closed is True
