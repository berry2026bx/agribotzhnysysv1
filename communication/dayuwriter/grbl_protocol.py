from dataclasses import dataclass
from enum import Enum
from math import isfinite


READ_ONLY_LINE_COMMANDS = frozenset({"$I", "$$", "$#", "$G"})
READ_ONLY_REALTIME_COMMANDS = frozenset({"?"})
MAX_JOG_DISTANCE_MM = 5.0
MAX_XY_FEED_MM_MIN = 100.0
MAX_Z_FEED_MM_MIN = 50.0


class LineKind(str, Enum):
    EMPTY = "empty"
    BANNER = "banner"
    ACK = "ack"
    ERROR = "error"
    ALARM = "alarm"
    STATUS = "status"
    MESSAGE = "message"
    SETTING = "setting"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ParsedLine:
    raw: str
    kind: LineKind


@dataclass(frozen=True)
class JogCommand:
    axis: str
    distance_mm: float
    feed_mm_min: float


def validate_jog(command: JogCommand) -> JogCommand:
    axis = command.axis.upper()
    if axis not in {"X", "Y", "Z"}:
        raise ValueError(f"unsupported jog axis: {command.axis!r}")

    distance_mm = float(command.distance_mm)
    if not isfinite(distance_mm) or distance_mm == 0 or abs(distance_mm) > MAX_JOG_DISTANCE_MM:
        raise ValueError(f"unsafe jog distance: {command.distance_mm!r}")

    feed_mm_min = float(command.feed_mm_min)
    max_feed = MAX_Z_FEED_MM_MIN if axis == "Z" else MAX_XY_FEED_MM_MIN
    if not isfinite(feed_mm_min) or feed_mm_min <= 0 or feed_mm_min > max_feed:
        raise ValueError(f"unsafe jog feed: {command.feed_mm_min!r}")

    return JogCommand(axis=axis, distance_mm=distance_mm, feed_mm_min=feed_mm_min)


def encode_jog(command: JogCommand) -> bytes:
    normalized = validate_jog(command)
    return (
        f"$J=G91 {normalized.axis}{normalized.distance_mm:g} "
        f"F{normalized.feed_mm_min:g}\n"
    ).encode("ascii")


def assert_read_only(command: str) -> None:
    normalized = command.strip()
    allowed = READ_ONLY_LINE_COMMANDS | READ_ONLY_REALTIME_COMMANDS
    if normalized not in allowed:
        raise ValueError(f"state-changing command is prohibited: {command!r}")


def encode_read_only(command: str) -> bytes:
    normalized = command.strip()
    assert_read_only(normalized)
    if normalized in READ_ONLY_REALTIME_COMMANDS:
        return normalized.encode("ascii")
    return f"{normalized}\n".encode("ascii")


def parse_line(raw: str) -> ParsedLine:
    text = raw.strip()
    if not text:
        kind = LineKind.EMPTY
    elif text.startswith("Grbl "):
        kind = LineKind.BANNER
    elif text == "ok":
        kind = LineKind.ACK
    elif text.startswith("error:"):
        kind = LineKind.ERROR
    elif text.startswith("ALARM:"):
        kind = LineKind.ALARM
    elif text.startswith("<") and text.endswith(">"):
        kind = LineKind.STATUS
    elif text.startswith("[") and text.endswith("]"):
        kind = LineKind.MESSAGE
    elif text.startswith("$") and "=" in text:
        kind = LineKind.SETTING
    else:
        kind = LineKind.UNKNOWN
    return ParsedLine(raw=text, kind=kind)
