import importlib
from argparse import Namespace

from communication.dayuwriter.grbl_controller import (
    ControllerError,
    GrblStatus,
    JogResult,
)
from communication.dayuwriter.grbl_protocol import JogCommand
from communication.dayuwriter import grbl_jog


class FakeController:
    def __init__(self, result=None, error=None):
        self.result = result or JogResult(
            command=JogCommand("X", 1.0, 10.0),
            acceptance="ok",
            final_status=GrblStatus("<Idle|MPos:1.000,0.000,0.000|FS:0,0>", "Idle"),
        )
        self.error = error
        self.jog_calls = []
        self.status_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def jog(self, command):
        self.jog_calls.append(command)
        if self.error:
            raise self.error
        return self.result

    def status(self):
        self.status_calls += 1
        return GrblStatus("<Idle|MPos:0.000,0.000,0.000|FS:0,0>", "Idle")


def _args(**overrides):
    values = {"port": "COM9", "axis": "x", "distance": 1.0, "feed": 10.0}
    values.update(overrides)
    return Namespace(**values)


def test_invalid_jog_is_rejected_before_controller_factory(capsys):
    calls = []

    def factory(port):
        calls.append(port)
        raise AssertionError("factory must not be called")

    assert grbl_jog.run(_args(distance=99), factory) == 2
    assert calls == []
    assert "unsafe jog distance" in capsys.readouterr().err


def test_valid_jog_opens_controller_and_calls_jog_once(capsys):
    controller = FakeController()
    calls = []

    def factory(port):
        calls.append(port)
        return controller

    assert grbl_jog.run(_args(), factory) == 0
    assert calls == ["COM9"]
    assert len(controller.jog_calls) == 1
    assert controller.status_calls == 1
    assert controller.jog_calls[0] == JogCommand("X", 1.0, 10.0)
    output = capsys.readouterr().out
    assert "pre: <Idle|MPos:0.000,0.000,0.000|FS:0,0>" in output
    assert "accepted: ok" in output
    assert "final: " in output
    assert controller.result.final_status.raw in output


def test_controller_failure_returns_one(capsys):
    controller = FakeController(error=ControllerError("serial failed"))
    assert grbl_jog.run(_args(), lambda _port: controller) == 1
    assert "serial failed" in capsys.readouterr().err


def test_import_is_inert(monkeypatch):
    monkeypatch.setattr(grbl_jog, "GrblController", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()))
    importlib.reload(grbl_jog)


def test_parser_accepts_case_variants():
    parser = grbl_jog.build_parser()
    args = parser.parse_args(["--port", "COM3", "--axis", "z", "--distance", "0.5", "--feed", "5"])
    assert args.axis == "z"
