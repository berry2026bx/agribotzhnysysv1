from collections import deque

from communication.dayuwriter.grbl_console import run_console
from communication.dayuwriter.grbl_controller import GrblStatus, JogResult
from communication.dayuwriter.grbl_protocol import JogCommand


class FakeController:
    def __init__(self, port: str) -> None:
        self.port = port
        self.commands: list[JogCommand] = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.closed = True

    def status(self) -> GrblStatus:
        return GrblStatus("<Idle|MPos:0.000,0.000,0.000>", "Idle")

    def jog(self, command: JogCommand) -> JogResult:
        normalized = JogCommand(command.axis.upper(), float(command.distance_mm), float(command.feed_mm_min))
        self.commands.append(normalized)
        return JogResult(
            normalized,
            "ok",
            GrblStatus("<Idle|MPos:5.000,0.000,0.000>", "Idle"),
        )


class FakeFactory:
    def __init__(self) -> None:
        self.instance: FakeController | None = None

    def __call__(self, port: str) -> FakeController:
        self.instance = FakeController(port)
        return self.instance


def scripted_input(*commands: str):
    values = deque(commands)
    return lambda _prompt: values.popleft()


def test_console_keeps_one_controller_open_for_multiple_commands() -> None:
    factory = FakeFactory()
    output: list[str] = []

    result = run_console(
        "COM3",
        controller_factory=factory,
        input_fn=scripted_input("status", "jog X 5 100", "jog Y -2 50", "quit"),
        output_fn=output.append,
    )

    assert result == 0
    assert factory.instance is not None
    assert factory.instance.port == "COM3"
    assert factory.instance.commands == [
        JogCommand("X", 5.0, 100.0),
        JogCommand("Y", -2.0, 50.0),
    ]
    assert factory.instance.closed
    assert any(line.startswith("connected: <Idle|") for line in output)
    assert output.count("accepted: ok") == 2


def test_console_rejects_bad_input_without_moving() -> None:
    factory = FakeFactory()
    output: list[str] = []

    result = run_console(
        "COM3",
        controller_factory=factory,
        input_fn=scripted_input("jog X six 50", "jog X 1", "unknown", "quit"),
        output_fn=output.append,
    )

    assert result == 0
    assert factory.instance is not None
    assert factory.instance.commands == []
    assert any(line.startswith("invalid jog:") for line in output)
    assert any(line.startswith("usage: jog") for line in output)
    assert any(line.startswith("unknown command:") for line in output)


def test_console_eof_closes_cleanly() -> None:
    factory = FakeFactory()
    output: list[str] = []

    def eof(_prompt: str) -> str:
        raise EOFError

    assert run_console("COM3", controller_factory=factory, input_fn=eof, output_fn=output.append) == 0
    assert factory.instance is not None and factory.instance.closed
    assert output[-1] == "closed"
