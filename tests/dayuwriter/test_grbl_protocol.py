import pytest

from communication.dayuwriter.grbl_protocol import (
    LineKind,
    assert_read_only,
    encode_read_only,
    parse_line,
)


@pytest.mark.parametrize("command", ["$I", "$$", "$#", "$G", "?"])
def test_read_only_commands_are_allowed(command: str) -> None:
    assert_read_only(command)


@pytest.mark.parametrize(
    "command",
    ["$100=80", "$RST=*", "$H", "G92 X0", "G0 X1", "G1 X1", "$J=G91 X1 F50"],
)
def test_state_changing_commands_are_rejected(command: str) -> None:
    with pytest.raises(ValueError):
        assert_read_only(command)


def test_read_only_encoding_distinguishes_realtime_command() -> None:
    assert encode_read_only("$I") == b"$I\n"
    assert encode_read_only("?") == b"?"


@pytest.mark.parametrize(
    ("raw", "expected_kind"),
    [
        ("Grbl 1.1f kvenjoy.com ['$' for help]", LineKind.BANNER),
        ("ok", LineKind.ACK),
        ("error:20", LineKind.ERROR),
        ("ALARM:1", LineKind.ALARM),
        ("<Idle|MPos:0.000,0.000,0.000|FS:0,0>", LineKind.STATUS),
        ("[VER:1.1f.20170801:]", LineKind.MESSAGE),
        ("$100=80.000", LineKind.SETTING),
        ("unclassified text", LineKind.UNKNOWN),
    ],
)
def test_parse_line_preserves_raw_text(raw: str, expected_kind: LineKind) -> None:
    parsed = parse_line(raw)
    assert parsed.raw == raw
    assert parsed.kind is expected_kind

