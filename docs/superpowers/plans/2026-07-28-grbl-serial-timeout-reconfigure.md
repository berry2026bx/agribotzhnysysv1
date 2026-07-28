# GRBL Serial Timeout Reconfigure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent redundant pySerial COM-port reconfiguration during ordinary GRBL status polling while retaining controller write-deadline enforcement.

**Architecture:** `_write_until` currently assigns `write_timeout` even when the desired value equals the configured value. It will assign and restore that property only for a shorter remaining deadline. A fake serial will simulate a driver that rejects runtime timeout changes.

**Tech Stack:** Python 3.11, pySerial 3.5, pytest 9.1.

## Global Constraints

- Do not change `$J=G91`, distance caps, feeds, bounds, GRBL firmware, or physical motion behavior.
- Preserve short-deadline write capping and `ControllerError` behavior.
- Do not add retries, automatic recovery, or RealSense/dashboard changes.
- Verify focused controller tests and the full pytest suite before live motion.

---

### Task 1: Avoid Equal-Timeout COM Reconfiguration

**Files:**
- Modify: `tests/dayuwriter/test_grbl_controller.py:25-62`
- Modify: `tests/dayuwriter/test_grbl_controller.py:129-141`
- Modify: `communication/dayuwriter/grbl_controller.py:201-221`

**Interfaces:**
- Consumes: `GrblController.status() -> GrblStatus`, `FakeFactory`, and `FakeSerial`.
- Produces: `_write_until` avoids runtime serial-property assignment when `min(write_timeout_s, remaining)` equals `write_timeout_s`.

- [x] **Step 1: Write the failing test**

Extend `FakeSerial` with backing field `_write_timeout`, a `runtime_write_timeout_updates: list[float]`, and a `write_timeout` property whose setter raises `OSError("runtime serial timeout reconfiguration rejected")` when `fail_runtime_write_timeout_reconfigure` is true. Add this test after `test_status_writes_realtime_question_and_parses_state`:

```python
def test_status_does_not_reconfigure_an_equal_write_timeout() -> None:
    controller, factory, _ = make_controller()
    controller.open()
    serial_port = factory.instances[0]
    serial_port.fail_runtime_write_timeout_reconfigure = True
    serial_port.reads.append(b"<Idle|MPos:0,0,0|FS:0,0>\r\n")

    result = controller.status()

    assert result == GrblStatus(raw="<Idle|MPos:0,0,0|FS:0,0>", state="Idle")
    assert serial_port.writes == [b"?"]
    assert serial_port.runtime_write_timeout_updates == []
```

- [x] **Step 2: Verify RED**

Run `python -m pytest tests/dayuwriter/test_grbl_controller.py::test_status_does_not_reconfigure_an_equal_write_timeout -q`.

Expected: failure because current `_write_until` sets `serial_port.write_timeout` despite the equal `1.0` second value.

- [x] **Step 3: Implement GREEN**

In `communication/dayuwriter/grbl_controller.py`, compute `temporary_timeout = min(self.write_timeout_s, remaining)`. Set and restore `serial_port.write_timeout` only when `temporary_timeout < self.write_timeout_s`. Retain the trace call, `serial_port.write(payload)`, and existing exception conversion.

- [x] **Step 4: Verify focused tests**

Run `python -m pytest tests/dayuwriter/test_grbl_controller.py -q`.

Expected: all controller tests pass; the existing short-deadline test still verifies temporary lowering for `0.3` seconds.

- [x] **Step 5: Verify complete suite**

Run `python -m pytest -q -p no:cacheprovider --basetemp "$env:TEMP\dayuwriter-all-tests"`.

Expected: all tests pass.

- [x] **Step 6: Commit the implementation**

Run:

```powershell
git add communication/dayuwriter/grbl_controller.py tests/dayuwriter/test_grbl_controller.py docs/superpowers/plans/2026-07-28-grbl-serial-timeout-reconfigure.md
git commit -m "fix: avoid redundant GRBL serial timeout reconfigure"
```
