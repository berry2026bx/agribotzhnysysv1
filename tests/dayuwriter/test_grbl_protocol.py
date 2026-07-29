import pytest

from communication.dayuwriter.grbl_protocol import (
    JogCommand,
    LineKind,
    assert_read_only,
    encode_jog,
    encode_read_only,
    parse_line,
    validate_jog,
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


def test_validate_jog_normalizes_axis_and_numeric_values() -> None:
    command = validate_jog(JogCommand(axis="x", distance_mm="1.5", feed_mm_min="50"))

    assert command == JogCommand(axis="X", distance_mm=1.5, feed_mm_min=50.0)


def test_encode_jog_uses_exact_grbl_relative_jog_format() -> None:
    assert encode_jog(JogCommand(axis="X", distance_mm=1, feed_mm_min=50)) == b"$J=G91 G21 X1 F50\n"


def test_encode_jog_uses_fixed_decimal_format_without_exponents() -> None:
    encoded = encode_jog(JogCommand(axis="X", distance_mm=1.234, feed_mm_min=0.001))

    assert encoded == b"$J=G91 G21 X1.234 F0.001\n"
    assert b"e" not in encoded.lower()


def test_validate_jog_accepts_minimum_distance_and_feed_resolution() -> None:
    command = validate_jog(JogCommand(axis="X", distance_mm=0.001, feed_mm_min=0.001))

    assert command == JogCommand(axis="X", distance_mm=0.001, feed_mm_min=0.001)


def test_validate_jog_accepts_the_five_hundred_mm_per_min_xy_commissioning_limit() -> None:
    command = validate_jog(JogCommand(axis="X", distance_mm=5.0, feed_mm_min=500.0))

    assert command == JogCommand(axis="X", distance_mm=5.0, feed_mm_min=500.0)


@pytest.mark.parametrize(
    "command",
    [
        JogCommand(axis="A", distance_mm=1, feed_mm_min=50),
        JogCommand(axis="X", distance_mm=0, feed_mm_min=50),
        JogCommand(axis="X", distance_mm=1e-7, feed_mm_min=50),
        JogCommand(axis="X", distance_mm=float("nan"), feed_mm_min=50),
        JogCommand(axis="X", distance_mm=float("inf"), feed_mm_min=50),
        JogCommand(axis="X", distance_mm=5.1, feed_mm_min=50),
        JogCommand(axis="X", distance_mm=-5.1, feed_mm_min=50),
        JogCommand(axis="X", distance_mm=1, feed_mm_min=0),
        JogCommand(axis="X", distance_mm=1, feed_mm_min=1e-7),
        JogCommand(axis="X", distance_mm=1, feed_mm_min=-1),
        JogCommand(axis="X", distance_mm=1, feed_mm_min=float("nan")),
        JogCommand(axis="X", distance_mm=1, feed_mm_min=float("inf")),
        JogCommand(axis="X", distance_mm=1, feed_mm_min=500.1),
        JogCommand(axis="Z", distance_mm=1, feed_mm_min=50.1),
    ],
)
def test_validate_jog_rejects_unsafe_commands(command: JogCommand) -> None:
    with pytest.raises(ValueError):
        validate_jog(command)
