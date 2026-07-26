from dataclasses import dataclass
from enum import Enum


READ_ONLY_LINE_COMMANDS = frozenset({"$I", "$$", "$#", "$G"})
READ_ONLY_REALTIME_COMMANDS = frozenset({"?"})


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

