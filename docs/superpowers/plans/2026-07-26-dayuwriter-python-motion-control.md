# DayuWriter Python Motion Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a tested Python controller and CLI that keep one GRBL serial connection open and perform one explicit, bounded relative jog.

**Architecture:** Extend the existing protocol module with pure jog validation/encoding, then add a persistent `GrblController` that separates connection, status, command acceptance, and motion completion. A thin CLI validates all motion arguments before opening `COM3`, runs exactly one jog, reports raw evidence, and closes the port.

**Tech Stack:** Python 3.11, pySerial 3.5, pytest 9.1.1, GRBL 1.1f, Windows 11

## Global Constraints

- Serial configuration is 115200 baud, 8-N-1, no flow control, finite read and write timeouts.
- Opening/importing the controller must never cause motion.
- Only `$J=G91` relative jogs are permitted; arbitrary G-code is prohibited.
- Maximum absolute distance per invocation is 5 mm.
- Maximum XY feed is 100 mm/min; maximum Z feed is 50 mm/min.
- A jog may be sent only after a current `Idle` status is received.
- `ok` means command acceptance only; completion requires a later `Idle` status.
- No `G92`, `$H`, `G0`, `G1`, GRBL setting write, or firmware operation is permitted.
- Current `$3=4` is preserved; positive Z physically moves the pen carriage downward.
- `P0` is a manual physical reference, not a GRBL machine origin.

---

## File Map

- `communication/dayuwriter/grbl_protocol.py`: pure command validation, encoding, and response classification.
- `communication/dayuwriter/grbl_controller.py`: persistent serial lifecycle, status precondition, command acceptance, and final-Idle polling.
- `communication/dayuwriter/grbl_jog.py`: explicit one-jog command-line interface.
- `tests/dayuwriter/test_grbl_protocol.py`: protocol boundary tests.
- `tests/dayuwriter/test_grbl_controller.py`: fake-serial controller tests.
- `tests/dayuwriter/test_grbl_jog.py`: CLI validation and lifecycle tests.
- `docs/dayuwriter/python-control.md`: operator commands, coordinate limitations, and live-test checklist.

### Task 1: Bounded Relative Jog Protocol

**Files:**
- Modify: `communication/dayuwriter/grbl_protocol.py`
- Modify: `tests/dayuwriter/test_grbl_protocol.py`

**Interfaces:**
- Produces: `JogCommand(axis: str, distance_mm: float, feed_mm_min: float)`
- Produces: `validate_jog(command: JogCommand) -> JogCommand`
- Produces: `encode_jog(command: JogCommand) -> bytes`

- [ ] **Step 1: Write failing validation and encoding tests**

Append tests that require exact bytes and reject invalid axes, zero/non-finite distance, excessive distance, non-positive/non-finite feed, and axis-specific feed excess:

```python
from math import inf, nan

from communication.dayuwriter.grbl_protocol import JogCommand, encode_jog


def test_encode_jog_uses_relative_grbl_jog_syntax() -> None:
    assert encode_jog(JogCommand("x", 1.0, 50.0)) == b"$J=G91 X1 F50\n"


@pytest.mark.parametrize(
    "command",
    [
        JogCommand("A", 1, 50),
        JogCommand("X", 0, 50),
        JogCommand("X", nan, 50),
        JogCommand("X", inf, 50),
        JogCommand("X", 5.01, 50),
        JogCommand("X", 1, 0),
        JogCommand("X", 1, nan),
        JogCommand("X", 1, 100.01),
        JogCommand("Z", 1, 50.01),
    ],
)
def test_encode_jog_rejects_unsafe_values(command: JogCommand) -> None:
    with pytest.raises(ValueError):
        encode_jog(command)
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```powershell
conda run -n dayuwriter-control pytest tests/dayuwriter/test_grbl_protocol.py -v
```

Expected: collection fails because `JogCommand` and `encode_jog` are not defined.

- [ ] **Step 3: Implement the minimal pure protocol API**

Add the following implementation without serial imports or side effects:

```python
from math import isfinite

MAX_JOG_DISTANCE_MM = 5.0
MAX_XY_FEED_MM_MIN = 100.0
MAX_Z_FEED_MM_MIN = 50.0


@dataclass(frozen=True)
class JogCommand:
    axis: str
    distance_mm: float
    feed_mm_min: float


def validate_jog(command: JogCommand) -> JogCommand:
    axis = command.axis.upper()
    distance = float(command.distance_mm)
    feed = float(command.feed_mm_min)
    if axis not in {"X", "Y", "Z"}:
        raise ValueError(f"invalid jog axis: {command.axis!r}")
    if not isfinite(distance) or distance == 0 or abs(distance) > MAX_JOG_DISTANCE_MM:
        raise ValueError(f"jog distance must be finite, non-zero, and <= {MAX_JOG_DISTANCE_MM} mm")
    max_feed = MAX_Z_FEED_MM_MIN if axis == "Z" else MAX_XY_FEED_MM_MIN
    if not isfinite(feed) or feed <= 0 or feed > max_feed:
        raise ValueError(f"{axis} feed must be finite, positive, and <= {max_feed} mm/min")
    return JogCommand(axis, distance, feed)


def encode_jog(command: JogCommand) -> bytes:
    checked = validate_jog(command)
    return (
        f"$J=G91 {checked.axis}{checked.distance_mm:g} "
        f"F{checked.feed_mm_min:g}\n"
    ).encode("ascii")
```

- [ ] **Step 4: Run the complete protocol tests**

Run: `conda run -n dayuwriter-control pytest tests/dayuwriter/test_grbl_protocol.py -v`

Expected: all existing read-only tests and new jog tests pass.

- [ ] **Step 5: Commit the protocol boundary**

```powershell
git add communication/dayuwriter/grbl_protocol.py tests/dayuwriter/test_grbl_protocol.py
git commit -m "comm: validate bounded GRBL jogs"
```

### Task 2: Persistent GRBL Controller

**Files:**
- Create: `communication/dayuwriter/grbl_controller.py`
- Create: `tests/dayuwriter/test_grbl_controller.py`

**Interfaces:**
- Consumes: `JogCommand`, `encode_jog`, `parse_line`, and `LineKind`
- Produces: `ControllerError`, `GrblStatus`, `JogResult`, and `GrblController`
- Produces methods: `open()`, `close()`, `status()`, `jog(command)`, `__enter__()`, `__exit__()`

- [ ] **Step 1: Write fake-serial tests for fail-closed behavior**

Create tests with a fake serial factory and scripted responses. Verify these exact cases:

```python
from collections import deque


class FakeSerial:
    def __init__(self, reads: list[bytes]) -> None:
        self.reads = deque(reads)
        self.writes: list[bytes] = []
        self.closed = False

    def reset_input_buffer(self) -> None:
        pass

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)

    def readline(self) -> bytes:
        return self.reads.popleft() if self.reads else b""

    def close(self) -> None:
        self.closed = True


class FakeSerialFactory:
    def __init__(self, reads: list[bytes]) -> None:
        self.instance = FakeSerial(reads)

    def __call__(self, **kwargs) -> FakeSerial:
        return self.instance


def test_open_and_status_send_no_motion() -> None:
    fake = FakeSerialFactory(reads=[b"<Idle|MPos:0.000,0.000,0.000>\r\n"])
    with GrblController("COM3", serial_factory=fake, startup_delay_s=0) as controller:
        status = controller.status()
    assert status.state == "Idle"
    assert fake.instance.writes == [b"?"]
    assert fake.instance.closed


def test_jog_requires_idle_before_writing_motion() -> None:
    fake = FakeSerialFactory(reads=[b"<Hold|MPos:0.000,0.000,0.000>\r\n"])
    with GrblController("COM3", serial_factory=fake, startup_delay_s=0) as controller:
        with pytest.raises(ControllerError, match="not Idle"):
            controller.jog(JogCommand("X", 1, 50))
    assert fake.instance.writes == [b"?"]


def test_ok_is_not_treated_as_motion_completion() -> None:
    fake = FakeSerialFactory(
        reads=[
            b"<Idle|MPos:0.000,0.000,0.000>\r\n",
            b"ok\r\n",
            b"<Jog|MPos:0.500,0.000,0.000>\r\n",
            b"<Idle|MPos:1.000,0.000,0.000>\r\n",
        ]
    )
    with GrblController("COM3", serial_factory=fake, startup_delay_s=0) as controller:
        result = controller.jog(JogCommand("X", 1, 50))
    assert result.acceptance == "ok"
    assert result.final_status.state == "Idle"
    assert fake.instance.writes == [b"?", b"$J=G91 X1 F50\n", b"?", b"?"]
```

Also test `error:`, `ALARM:`, status timeout, acceptance timeout, completion timeout, and closure after exceptions.

- [ ] **Step 2: Run controller tests and verify import failure**

Run: `conda run -n dayuwriter-control pytest tests/dayuwriter/test_grbl_controller.py -v`

Expected: FAIL because `grbl_controller.py` does not exist.

- [ ] **Step 3: Implement controller data models and lifecycle**

Use these public types and constructor defaults:

```python
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
        serial_factory=serial.Serial,
        clock=time.monotonic,
        sleeper=time.sleep,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.read_timeout_s = read_timeout_s
        self.write_timeout_s = write_timeout_s
        self.startup_delay_s = startup_delay_s
        self.response_deadline_s = response_deadline_s
        self.completion_deadline_s = completion_deadline_s
        self.poll_interval_s = poll_interval_s
        self._serial_factory = serial_factory
        self._clock = clock
        self._sleeper = sleeper
        self._serial = None
```

`open()` must configure 8-N-1 with `xonxoff=False`, `rtscts=False`, and `dsrdtr=False`, wait `startup_delay_s`, and clear only stale input. It must not write bytes. `close()` must be idempotent, and context-manager exit must always close.

- [ ] **Step 4: Implement status and jog state machines**

Implement `status()` to send `b"?"`, require a `<...>` response before the deadline, and extract the first pipe-delimited field as the state. Implement `jog()` in this order:

```python
checked = validate_jog(command)
pre_status = self.status()
if pre_status.state != "Idle":
    raise ControllerError(f"GRBL is not Idle: {pre_status.raw}")
self._serial.write(encode_jog(checked))
acceptance = self._wait_for_acceptance()
final_status = self._wait_until_idle()
return JogResult(checked, acceptance, final_status)
```

`_wait_for_acceptance()` must raise immediately on `error:` or `ALARM:`. `_wait_until_idle()` must repeatedly call `status()`, return only on `Idle`, and raise on deadline without sending another jog.

- [ ] **Step 5: Run focused and full offline tests**

Run:

```powershell
conda run -n dayuwriter-control pytest tests/dayuwriter/test_grbl_controller.py -v
conda run -n dayuwriter-control pytest tests/dayuwriter -v
```

Expected: all tests pass without opening a real COM port.

- [ ] **Step 6: Commit the persistent controller**

```powershell
git add communication/dayuwriter/grbl_controller.py tests/dayuwriter/test_grbl_controller.py
git commit -m "comm: add persistent GRBL controller"
```

### Task 3: Explicit One-Jog CLI

**Files:**
- Create: `communication/dayuwriter/grbl_jog.py`
- Create: `tests/dayuwriter/test_grbl_jog.py`

**Interfaces:**
- Consumes: `JogCommand`, `validate_jog`, `GrblController`, and `ControllerError`
- Produces: `build_parser() -> argparse.ArgumentParser`
- Produces: `run(args, controller_factory=GrblController) -> int`
- Produces: `main() -> int`

- [ ] **Step 1: Write CLI tests before implementation**

Test that missing explicit arguments fail, invalid values are rejected before the controller factory is called, and one valid invocation creates exactly one jog:

```python
class FakeController:
    def __init__(self) -> None:
        self.commands: list[JogCommand] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def jog(self, command: JogCommand) -> JogResult:
        self.commands.append(command)
        return JogResult(command, "ok", GrblStatus("<Idle|MPos:1.000,0.000,0.000>", "Idle"))


class FakeControllerFactory:
    def __init__(self) -> None:
        self.instance = FakeController()

    def __call__(self, port: str) -> FakeController:
        assert port == "COM3"
        return self.instance


def test_invalid_jog_does_not_open_controller() -> None:
    opened = False

    def factory(*args, **kwargs):
        nonlocal opened
        opened = True
        raise AssertionError("must not open")

    namespace = argparse.Namespace(port="COM3", axis="X", distance=6.0, feed=50.0)
    assert run(namespace, controller_factory=factory) == 2
    assert not opened


def test_valid_cli_runs_exactly_one_jog(capsys) -> None:
    fake = FakeControllerFactory()
    namespace = argparse.Namespace(port="COM3", axis="X", distance=1.0, feed=50.0)
    assert run(namespace, controller_factory=fake) == 0
    assert fake.instance.commands == [JogCommand("X", 1.0, 50.0)]
    assert "final: <Idle|" in capsys.readouterr().out
```

- [ ] **Step 2: Run CLI tests and verify they fail**

Run: `conda run -n dayuwriter-control pytest tests/dayuwriter/test_grbl_jog.py -v`

Expected: FAIL because `grbl_jog.py` does not exist.

- [ ] **Step 3: Implement argument parsing and pre-open validation**

The parser must require all arguments:

```python
parser.add_argument("--port", required=True)
parser.add_argument("--axis", required=True, choices=("X", "Y", "Z", "x", "y", "z"))
parser.add_argument("--distance", required=True, type=float)
parser.add_argument("--feed", required=True, type=float)
```

`run()` must instantiate and validate `JogCommand` before entering the controller context. It must print the final raw status and return `2` for local validation, `1` for controller/serial failures, and `0` only after final `Idle`.

- [ ] **Step 4: Verify module import is inert**

Add and run:

```python
def test_import_does_not_open_serial_or_move() -> None:
    completed = subprocess.run(
        [sys.executable, "-c", "import communication.dayuwriter.grbl_jog"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert completed.stdout == ""
    assert completed.stderr == ""
```

- [ ] **Step 5: Run CLI and full offline tests**

Run:

```powershell
conda run -n dayuwriter-control pytest tests/dayuwriter/test_grbl_jog.py -v
conda run -n dayuwriter-control pytest tests/dayuwriter -v
```

Expected: all tests pass with no real serial access.

- [ ] **Step 6: Commit the CLI**

```powershell
git add communication/dayuwriter/grbl_jog.py tests/dayuwriter/test_grbl_jog.py
git commit -m "comm: add bounded GRBL jog CLI"
```

### Task 4: Operator Documentation and Controlled Live Verification

**Files:**
- Create: `docs/dayuwriter/python-control.md`
- Create after live test: `docs/dayuwriter/baseline/2026-07-26-python-controller-x1.md`

**Interfaces:**
- Consumes CLI: `python -m communication.dayuwriter.grbl_jog --port COM3 --axis X --distance 1 --feed 50`
- Produces an operator procedure and immutable live-test evidence.

- [ ] **Step 1: Write the operator guide**

Document the exact safe workflow:

```markdown
1. Keep the pen clear and start from the marked P0 area.
2. Connect USB and motor power; do not open another serial application.
3. Activate `dayuwriter-control`.
4. Run a read-only status capture first.
5. Run one explicit X jog of 1 mm at 50 mm/min.
6. Confirm physical movement separately from the GRBL response.
7. Do not treat MPos after reconnect as retained physical position.
8. Record Z convention: positive Z moves downward.
```

Include the exact Conda activation and CLI commands, limit table, exit codes, and prohibition on concurrent UGS/micro-carving software.

- [ ] **Step 2: Run formatting and offline verification**

Run:

```powershell
git diff --check
conda run -n dayuwriter-control pytest tests/dayuwriter -v
```

Expected: no whitespace errors and all tests pass.

- [ ] **Step 3: Commit documentation before hardware access**

```powershell
git add docs/dayuwriter/python-control.md
git commit -m "docs: add Python motion control procedure"
git push
```

- [ ] **Step 4: Perform one controlled live X jog**

Preconditions: user confirms pen clearance, P0-area clearance, 12 V connected to CNC V3, and ability to disconnect 12 V immediately.

Run:

```powershell
conda run -n dayuwriter-control python -m communication.dayuwriter.grbl_jog `
  --port COM3 `
  --axis X `
  --distance 1 `
  --feed 50
```

Expected protocol result: precondition `Idle`, one `ok`, then final `Idle`. Required independent evidence: user physically observes the X movement. Stop without testing Y/Z if either evidence source fails.

- [ ] **Step 5: Record the live result and commit**

Write the exact command, raw pre/final status, exit code, and user physical observation to `docs/dayuwriter/baseline/2026-07-26-python-controller-x1.md`.

```powershell
git add docs/dayuwriter/baseline/2026-07-26-python-controller-x1.md
git commit -m "docs: record Python controller live test"
git push
```

### Task 5: Final Verification

**Files:**
- Verify only; modify files only if a test exposes a scoped defect.

**Interfaces:**
- Consumes all prior deliverables.
- Produces final test evidence and clean Git state.

- [ ] **Step 1: Run the complete offline suite**

Run: `conda run -n dayuwriter-control pytest tests/dayuwriter -v`

Expected: all tests pass.

- [ ] **Step 2: Verify CLI help without serial access**

Run: `conda run -n dayuwriter-control python -m communication.dayuwriter.grbl_jog --help`

Expected: exit code 0, required arguments displayed, and no COM port opened.

- [ ] **Step 3: Verify repository state and history**

Run:

```powershell
git diff --check
git status --short --branch
git log -5 --oneline
```

Expected: no uncommitted changes; execution branch contains protocol, controller, CLI, documentation, and live-evidence commits.
