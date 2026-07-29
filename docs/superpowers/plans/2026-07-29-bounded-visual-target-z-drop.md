# Bounded Visual Target Z Drop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a supervised visual-target command that moves to a red square in bounded XY segments and can then lower Z by at most 1 mm.

**Architecture:** `communication.dayuwriter.visual_follow` continues to consume a JSON snapshot from the display-only dashboard. It will convert the visual delta to axis-specific five-millimetre GRBL jogs and send them through one persistent `GrblController`; an optional final Z command is created only after explicit acknowledgement.

**Tech Stack:** Python 3.11, argparse, pyserial-backed `GrblController`, pytest.

## Global Constraints

- Dashboard serial ownership remains prohibited; it must advertise `motion_permission=display_only`.
- Require physical P0 re-alignment, a clear path, suspended pen, live 12 V, and at least 1 mm safe downward space before execution.
- Each GRBL jog is at most 5 mm; XY feed is at most 100 mm/min; Z+ is at most 1 mm at 50 mm/min.
- Reject an initial visual delta outside plus or minus 30 mm on either axis.
- Execute all XY segments and final `Idle` checks before an optional Z+ command.

---

### Task 1: Model The Bounded Target Sequence

**Files:**
- Modify: `communication/dayuwriter/visual_follow.py`
- Test: `tests/dayuwriter/test_visual_follow.py`

**Interfaces:**
- Produces `build_target_move_proposal(baseline, target, feed_mm_min=50.0, z_drop_mm=0.0) -> FollowProposal`.
- `FollowProposal.commands` contains X segments, then Y segments, then optional Z+.

- [ ] **Step 1: Write failing tests**

```python
def test_build_target_move_proposal_splits_xy_then_appends_z() -> None:
    proposal = build_target_move_proposal(
        FollowBaseline(1.927, 0.169),
        LiveTarget(13.927, 7.169),
        z_drop_mm=1.0,
    )
    assert proposal.commands == (
        JogCommand("X", 4.0, 50.0),
        JogCommand("X", 4.0, 50.0),
        JogCommand("X", 4.0, 50.0),
        JogCommand("Y", 3.5, 50.0),
        JogCommand("Y", 3.5, 50.0),
        JogCommand("Z", 1.0, 50.0),
    )
```

- [ ] **Step 2: Run the focused test to verify failure**

Run: `& 'C:\Users\Administrator\.conda\envs\dayuwriter-control\python.exe' -m pytest tests/dayuwriter/test_visual_follow.py::test_build_target_move_proposal_splits_xy_then_appends_z -q`

Expected: FAIL because `build_target_move_proposal` is not defined.

- [ ] **Step 3: Implement the smallest proposal builder**

Use `workspace.split_delta` for individual axes, construct `JogCommand`s in X/Y/Z order, call `validate_jog` for every command, reject XY deltas whose absolute value exceeds 30 mm, and reject Z drop outside `0..1` mm.

- [ ] **Step 4: Run the focused test to verify pass**

Run: `& 'C:\Users\Administrator\.conda\envs\dayuwriter-control\python.exe' -m pytest tests/dayuwriter/test_visual_follow.py::test_build_target_move_proposal_splits_xy_then_appends_z -q`

Expected: PASS.

### Task 2: Require Explicit Runtime Acknowledgements

**Files:**
- Modify: `communication/dayuwriter/visual_follow.py`
- Test: `tests/dayuwriter/test_visual_follow.py`

**Interfaces:**
- `run(args, ...) -> int` accepts `z_drop_mm` and `z_drop_preflight` from argparse.

- [ ] **Step 1: Write failing tests**

```python
def test_run_rejects_z_drop_without_z_preflight(capsys) -> None:
    assert visual_follow.run(
        args(execute=True, port="COM4", physical_preflight=True, z_drop_mm=1.0),
        fetcher=lambda _url: ready_payload(x=6.927, y=0.169),
    ) == 2
    assert "--z-drop-preflight" in capsys.readouterr().err
```

- [ ] **Step 2: Run the focused test to verify failure**

Run: `& 'C:\Users\Administrator\.conda\envs\dayuwriter-control\python.exe' -m pytest tests/dayuwriter/test_visual_follow.py::test_run_rejects_z_drop_without_z_preflight -q`

Expected: FAIL because the Z acknowledgement does not exist.

- [ ] **Step 3: Implement argparse and runner guards**

Add `--z-drop-mm` (default `0`) and `--z-drop-preflight`. Preview always returns without opening serial. Execution rejects a positive Z drop unless the Z acknowledgement is present, then passes the fully validated proposal to the existing persistent-controller executor.

- [ ] **Step 4: Run focused tests and suite**

Run: `& 'C:\Users\Administrator\.conda\envs\dayuwriter-control\python.exe' -m pytest tests/dayuwriter/test_visual_follow.py -q`

Expected: PASS.

### Task 3: Document And Verify The Command

**Files:**
- Modify: `docs/dayuwriter/17-visual-follow-first-operation.md`
- Test: `tests/dayuwriter/test_visual_follow.py`

- [ ] **Step 1: Write a failing execution-order test**

```python
def test_execute_target_move_uses_one_controller_and_z_is_last() -> None:
    controller = FakeController()
    proposal = FollowProposal(6.0, 0.0, (JogCommand("X", 3, 50), JogCommand("X", 3, 50), JogCommand("Z", 1, 50)))
    execute_follow("COM4", proposal, lambda _port: controller)
    assert controller.jog_calls[-1] == JogCommand("Z", 1, 50)
```

- [ ] **Step 2: Verify fail, make the minimal compatible executor update, then verify pass**

Run: `& 'C:\Users\Administrator\.conda\envs\dayuwriter-control\python.exe' -m pytest tests/dayuwriter/test_visual_follow.py::test_execute_target_move_uses_one_controller_and_z_is_last -q`

Expected: first FAIL if the test exposes missing capability; final PASS after the proposal builder and executor work together.

- [ ] **Step 3: Write operating instructions**

Document the exact preview and execution commands using baseline `1.927`, `0.169`, `COM4`, `--execute`, `--physical-preflight`, `--z-drop-mm 1`, and `--z-drop-preflight`. State that target distance is limited to 30 mm per axis, that each segment waits for `Idle`, and that the output is only rough supervised positioning.

- [ ] **Step 4: Run all verification**

Run: `& 'C:\Users\Administrator\.conda\envs\dayuwriter-control\python.exe' -m pytest -q -p no:cacheprovider --basetemp "$env:USERPROFILE\pytest-temp\dayuwriter-tests"`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add communication/dayuwriter/visual_follow.py tests/dayuwriter/test_visual_follow.py docs/dayuwriter/17-visual-follow-first-operation.md docs/superpowers
git commit -m "feat: add bounded visual target z drop"
git push origin codex/dayuwriter-recovery-execution
```
