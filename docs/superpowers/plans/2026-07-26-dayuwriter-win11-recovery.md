# DayuWriter Win11 Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Identify the current DayuWriter on Windows 11, capture its GRBL baseline without changing it, inspect the powered machine, and perform one short controlled jog.

**Architecture:** The workflow is a sequence of physical safety gates. Evidence from each gate is written to a dated test record before the next gate is allowed. Windows Device Manager establishes device identity; a bounded read-only serial tool captures GRBL state; only after mechanical and electrical inspection is 12 V connected and one low-energy jog attempted.

**Tech Stack:** Windows 11 Device Manager, Git, Conda, Python 3.11, pySerial 3.5+, pytest, GRBL 1.1 serial protocol

## Global Constraints

- Keep 12 V disconnected through completion and review of the USB/GRBL read-only baseline.
- Do not flash firmware or write GRBL EEPROM settings.
- Do not send `$H`, `G92`, `G0`, `G1`, or `$J=` before the motion gate.
- Never treat `Ctrl-X` as a physical emergency stop.
- Every serial wait must have a finite deadline.
- Use only live-discovered COM ports and live-captured settings.
- Do not upload seller archives, cracked software, third-party binaries, raw videos, credentials, or private data to the public repository.

---

## File Map

- `docs/dayuwriter/README.md`: entry point, phase status, and safety rules.
- `docs/dayuwriter/baseline/YYYY-MM-DD-device-baseline.md`: append-only machine evidence record created from the template.
- `docs/dayuwriter/templates/device-baseline-template.md`: exact checklist and output fields.
- `environment/dayuwriter-control.yml`: reproducible recovery environment.
- `communication/dayuwriter/grbl_protocol.py`: pure parsing and command-classification functions with no serial I/O.
- `communication/dayuwriter/grbl_diag.py`: explicit-port, read-only GRBL capture CLI.
- `tests/dayuwriter/test_grbl_protocol.py`: parser and command-policy tests.
- `tests/dayuwriter/test_grbl_diag.py`: fake-serial tests for timeouts and read-only behavior.

### Task 1: Establish the Recovery Record

**Files:**
- Create: `docs/dayuwriter/README.md`
- Create: `docs/dayuwriter/templates/device-baseline-template.md`
- Create after USB inspection: `docs/dayuwriter/baseline/2026-07-26-device-baseline.md`

**Interfaces:**
- Consumes: observations from Device Manager, physical inspection, and GRBL output.
- Produces: the reviewed facts that later tasks may use as configuration.

- [ ] **Step 1: Confirm the initial physical state**

Required observation:

```text
USB disconnected: yes
12 V disconnected: yes
Carriage did not move during inspection: yes
Pen/tool clear of the work surface: yes
Direct access to the 12 V disconnect: yes
```

Stop if any answer is `no`.

- [ ] **Step 2: Record the unpowered hardware**

Record, without disassembling energized equipment:

```text
Controller board markings:
CNC shield markings:
A4988 count and orientation:
XY motor connector labels/positions:
Z motor connector label/position:
Limit switches physically present (X/Y/Z):
12 V adapter output label:
Visible damage, loose plugs, or exposed conductors:
Belt, pulley, set-screw, rail, lead-screw observations:
```

- [ ] **Step 3: Create the dated baseline from the template**

Expected result: a record exists but all not-yet-observed values are marked `not observed`; historical values are placed only in a clearly labeled history section.

- [ ] **Step 4: Commit the documentation skeleton**

```powershell
git add docs/dayuwriter
git commit -m "docs: add DayuWriter recovery record"
```

Expected: one commit containing only text documentation.

### Task 2: Identify the USB Device Without 12 V

**Files:**
- Modify: `docs/dayuwriter/baseline/2026-07-26-device-baseline.md`

**Interfaces:**
- Consumes: Windows Plug and Play observations.
- Produces: exact COM port, hardware identity, and driver status.

- [ ] **Step 1: Capture the before state**

Open Device Manager and expand both:

```text
Ports (COM & LPT)
Other devices
```

Expected current baseline: only the computer's pre-existing devices; earlier observation found `COM1`, but verify again.

- [ ] **Step 2: Connect USB only**

Keep 12 V physically disconnected. Connect the writer USB cable and wait for Plug and Play to finish.

Stop immediately if the controller becomes hot, smells abnormal, or any motor moves.

- [ ] **Step 3: Capture the after state**

For the new or changed device, record:

```text
Displayed name:
COM number:
Device status text:
Hardware IDs:
VID:
PID:
Driver provider:
Driver date:
Driver version:
Warning icon present:
```

Expected: one new USB serial device with no warning. Do not rename it and do not assume it is CH340 until its hardware ID supports that conclusion.

- [ ] **Step 4: Apply the driver decision**

If the port works without warning, install nothing.

If Windows reports an unknown device or warning, obtain the current official WCH package from:

```text
https://www.wch-ic.com/downloads/CH341SER_EXE.html
```

After installation, repeat the before/after comparison. Do not use `resource/上位机软件/奎享雕刻/驱动(ch340).EXE` because it is unsigned.

- [ ] **Step 5: Verify the port from PowerShell**

```powershell
Get-CimInstance Win32_SerialPort |
  Select-Object DeviceID, Name, PNPDeviceID, Manufacturer
```

Expected: the same COM number and hardware identity shown by Device Manager.

- [ ] **Step 6: Update and commit the evidence record**

```powershell
git add docs/dayuwriter/baseline/2026-07-26-device-baseline.md
git commit -m "docs: record DayuWriter USB identity"
```

### Task 3: Create the Isolated Diagnostic Environment

**Files:**
- Create: `environment/dayuwriter-control.yml`

**Interfaces:**
- Consumes: installed Conda 25.5.1.
- Produces: a Python 3.11 environment with pySerial and pytest; no camera stack yet.

- [ ] **Step 1: Write the environment manifest**

```yaml
name: dayuwriter-control
channels:
  - conda-forge
dependencies:
  - python=3.11
  - pip
  - pyserial>=3.5
  - pytest>=8
```

- [ ] **Step 2: Create the environment**

```powershell
conda env create -f environment/dayuwriter-control.yml
```

Expected: environment `dayuwriter-control` is created without modifying `base`.

- [ ] **Step 3: Activate and verify interpreter ownership**

```powershell
conda activate dayuwriter-control
python -c "import sys, serial; print(sys.executable); print(serial.__version__)"
python -m serial.tools.list_ports -v
```

Expected: Python path belongs to `dayuwriter-control`, pySerial is at least 3.5, and the port list agrees with Task 2.

- [ ] **Step 4: Commit the manifest**

```powershell
git add environment/dayuwriter-control.yml
git commit -m "comm: add DayuWriter serial environment"
```

### Task 4: Build a Read-Only GRBL Diagnostic Tool

**Files:**
- Create: `communication/dayuwriter/__init__.py`
- Create: `communication/dayuwriter/grbl_protocol.py`
- Create: `communication/dayuwriter/grbl_diag.py`
- Create: `tests/dayuwriter/test_grbl_protocol.py`
- Create: `tests/dayuwriter/test_grbl_diag.py`

**Interfaces:**
- Consumes: explicit `--port COMx`, serial lines, and a monotonic deadline.
- Produces: raw boot banner and responses to `$I`, `$$`, `$#`, `$G`, and `?`; returns nonzero on timeout or protocol error.

- [ ] **Step 1: Write policy tests that reject state-changing commands**

```python
import pytest

from communication.dayuwriter.grbl_protocol import assert_read_only


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
```

- [ ] **Step 2: Run the policy test and verify failure**

```powershell
pytest tests/dayuwriter/test_grbl_protocol.py -v
```

Expected: FAIL because `grbl_protocol.py` does not exist.

- [ ] **Step 3: Replace the policy test with the complete protocol test**

```python
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
```

- [ ] **Step 4: Implement the complete protocol module**

```python
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
```

Run:

```powershell
pytest tests/dayuwriter/test_grbl_protocol.py -v
```

Expected: all protocol tests pass. The parser classifies text only; it does not claim that reported coordinates are physically correct.

- [ ] **Step 5: Write complete fake-serial diagnostic tests**

```python
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
```

- [ ] **Step 6: Implement the diagnostic CLI**

```python
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
```

Required CLI:

```powershell
python -m communication.dayuwriter.grbl_diag --port COM7 --output <path>
```

The tool does not auto-select a port, clear buffers, send wake-up newlines, toggle 12 V, or allow motion/state-changing commands.

- [ ] **Step 7: Run the offline test suite**

```powershell
pytest tests/dayuwriter -v
```

Expected: all tests pass without a connected machine.

- [ ] **Step 8: Commit the diagnostic tool**

```powershell
git add communication/dayuwriter tests/dayuwriter
git commit -m "comm: add read-only GRBL diagnostics"
```

### Task 5: Capture and Review the Live GRBL Baseline

**Files:**
- Modify: `docs/dayuwriter/baseline/2026-07-26-device-baseline.md`
- Create: `docs/dayuwriter/baseline/2026-07-26-grbl-raw.txt`

**Interfaces:**
- Consumes: the exact COM port from Task 2 and the tested diagnostic CLI.
- Produces: raw firmware identity, settings, offsets, modal state, and realtime state.

- [ ] **Step 1: Confirm exclusive serial ownership**

Close UGS, Arduino Serial Monitor, vendor software, VS Code serial extensions, and any prior Python process.

- [ ] **Step 2: Run the read-only capture with 12 V disconnected**

Replace `COMx` only with the value observed in Task 2:

```powershell
python -m communication.dayuwriter.grbl_diag `
  --port COMx `
  --output docs/dayuwriter/baseline/2026-07-26-grbl-raw.txt
```

- [ ] **Step 3: Review the raw output before proceeding**

Required review fields:

```text
Boot banner:
$I build information:
$$ complete settings:
$# coordinate offsets:
$G modal state:
? controller state:
$20 soft limits:
$21 hard limits:
$22 homing:
$23 homing direction mask:
$100/$101/$102 steps per mm:
$110/$111/$112 maximum rates:
$120/$121/$122 accelerations:
$130/$131/$132 maximum travel:
```

Do not change a value merely because it differs from the historical `80`, `2000`, or `290 x 200` values.

- [ ] **Step 4: Stop on an unresolved controller state**

Do not continue to 12 V if the state is `Alarm`, `Door`, `Hold`, `Sleep`, malformed, or inconsistent between repeated queries.

- [ ] **Step 5: Commit the reviewed baseline**

```powershell
git add docs/dayuwriter/baseline
git commit -m "docs: capture DayuWriter GRBL baseline"
```

### Task 6: Inspect 12 V Operation and Perform the First Jog

**Files:**
- Modify: `docs/dayuwriter/baseline/2026-07-26-device-baseline.md`

**Interfaces:**
- Consumes: reviewed USB/GRBL baseline and physical inspection.
- Produces: verified first motion direction and a go/no-go decision for the Python-controller milestone.

- [ ] **Step 1: Disconnect all power and complete the mechanical review**

Verify belt tension, carriage freedom, pulley set screws, motor connectors, Z coupler, cable clearance, limit-switch presence, adapter output, and polarity.

- [ ] **Step 2: Reconnect USB, then 12 V, without motion commands**

Keep one hand ready to disconnect 12 V. Observe for 60 seconds without sending commands.

Stop for spontaneous movement, sustained vibration, abnormal sound, heat, smell, smoke, or arcing.

- [ ] **Step 3: Re-query status**

Use only `?` and record the resulting state. Do not unlock an alarm automatically.

- [ ] **Step 4: Prepare the motion envelope**

```text
Pen/tool raised or removed: yes
Carriage at least 20 mm from every boundary: yes
No cable can snag during a 1 mm move: yes
12 V disconnect reachable: yes
Only one operator issuing commands: yes
```

Stop if any answer is `no`.

- [ ] **Step 5: Send one 1 mm jog**

Only after explicit review of `$I`, `$$`, and `?`, send one conservative jog such as:

```text
$J=G91 X1 F50
```

The selected axis/sign may be changed based on physical clearance. Send the command once, then poll `?` with a finite deadline. Do not repeat by holding a GUI button.

- [ ] **Step 6: Record the physical result**

```text
Exact command:
Start state:
End state:
Reported coordinate change:
Observed carriage direction:
Measured approximate distance:
Noise/vibration:
Boundary clearance after move:
Suspected missed steps:
```

- [ ] **Step 7: Decide the milestone result**

Pass only if the move was short, smooth, directionally understood, and returned to `Idle` before the deadline. Any collision, stalling, vibration, unexplained diagonal motion, or coordinate inconsistency is a failure requiring diagnosis before another jog.

- [ ] **Step 8: Commit the test result**

```powershell
git add docs/dayuwriter/baseline/2026-07-26-device-baseline.md
git commit -m "test: record DayuWriter first jog"
```

## Final Verification

Run:

```powershell
pytest tests/dayuwriter -v
git status --short
git log --oneline --max-count=8
```

Expected:

```text
All offline tests pass.
Working tree is clean.
The USB identity, GRBL baseline, environment, diagnostic tool, and first-jog record each have reviewable commits.
No firmware, EEPROM, homing, G92, seller binary, or camera dependency was used.
```

After this milestone, write a separate implementation plan for the bounded Python motion controller. Do not begin D435i installation or detector integration until motion scale, direction, repeatability, and usable workspace are measured.
