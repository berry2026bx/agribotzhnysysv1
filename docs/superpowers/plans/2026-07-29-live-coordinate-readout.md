# Live Coordinate Readout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Display the live red-square X/Y coordinate relative to P0 prominently in the local dashboard.

**Architecture:** The existing `/state.json` polling function will call a small DOM renderer for the existing `machine_xy_mm` data. The renderer clears its values when the state is not a valid ready plane mapping.

**Tech Stack:** Python inline HTML, CSS, browser JavaScript, pytest.

## Global Constraints

- Preserve dashboard `motion_permission=display_only`.
- Do not add a GRBL command, serial-port call, or motion button.
- Render only finite X/Y values from a `ready` and `available` mapping.

---

### Task 1: Add The Fixed X/Y Readout

**Files:**
- Modify: `vision/realsense/live_red_target_dashboard.py`
- Test: `tests/realsense/test_live_red_target_dashboard.py`

**Interfaces:**
- Browser DOM ids: `target-coordinate`, `target-x`, `target-y`, and `target-coordinate-state`.
- `renderTargetCoordinate(state)` updates those fields every existing refresh interval.

- [x] **Step 1: Write the failing page-contract test**

```python
def test_dashboard_page_has_prominent_live_machine_xy_readout() -> None:
    page = _html_page()
    assert 'id="target-coordinate"' in page
    assert 'id="target-x"' in page
    assert 'id="target-y"' in page
    assert "function renderTargetCoordinate(state)" in page
```

- [x] **Step 2: Verify failure**

Run: `& 'C:\Users\Administrator\.conda\envs\dayuwriter-control\python.exe' -m pytest tests/realsense/test_live_red_target_dashboard.py::test_dashboard_page_has_prominent_live_machine_xy_readout -q -p no:cacheprovider --basetemp "$env:USERPROFILE\pytest-temp\dayuwriter-coordinate-readout-tests"`

Expected: FAIL because no coordinate-readout DOM elements exist.

- [x] **Step 3: Add the bounded display implementation**

Add the coordinate section and a renderer that formats a finite ready mapping to two decimal places with explicit sign. For non-ready states, clear X/Y to `--` and show an invalid-state label.

- [x] **Step 4: Verify and commit**

Run focused and full pytest commands with the dedicated `pytest-temp` base directory. Restart the display-only dashboard, reload the local page, and verify that the coordinate card visibly matches `/state.json`.

```powershell
git add vision/realsense/live_red_target_dashboard.py tests/realsense/test_live_red_target_dashboard.py docs/superpowers
git commit -m "feat: show live target coordinates"
git push origin codex/dayuwriter-recovery-execution
```
