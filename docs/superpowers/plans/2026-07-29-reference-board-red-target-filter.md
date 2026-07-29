# Reference-Board Red Target Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent red regions outside the A4 ArUco reference plane from replacing the intended paper target.

**Architecture:** `find_red_target` will accept an optional candidate predicate. The dashboard will create that predicate only from its ready reference-board homography and reject candidates whose projected machine coordinate is outside the physical A4 rectangle.

**Tech Stack:** Python 3.11, NumPy, pytest, existing ArUco board mapping.

## Global Constraints

- Preserve `motion_permission=display_only` in the dashboard.
- Do not open a serial port or send GRBL from this feature.
- Filter only when the reference tracker supplies a valid ready plane mapping.

---

### Task 1: Filter Candidate Selection By The Reference Plane

**Files:**
- Modify: `vision/realsense/red_target.py`
- Modify: `vision/realsense/live_red_target_dashboard.py`
- Test: `tests/realsense/test_red_target.py`

**Interfaces:**
- `find_red_target(rgb, config=None, *, candidate_filter=None) -> RedTarget | None`
- `_reference_board_candidate_filter(layout, pixel_to_machine) -> Callable[[RedTarget], bool]`

- [ ] **Step 1: Write the failing tests**

```python
def test_candidate_filter_rejects_a_larger_false_red_region() -> None:
    image = frame_with_inside_and_outside_red_regions()
    target = find_red_target(image, candidate_filter=lambda item: item.center_uv[0] > 20)
    assert target.center_uv == pytest.approx((50.0, 40.0), abs=0.2)
```

```python
def test_reference_board_filter_accepts_paper_coordinates_only() -> None:
    allow = _reference_board_candidate_filter(default_layout(), np.eye(3))
    assert allow(RedTarget((0.0, 0.0), 20, (0, 0, 4, 5), 1.0))
    assert not allow(RedTarget((500.0, 0.0), 20, (0, 0, 4, 5), 1.0))
```

- [ ] **Step 2: Verify tests fail**

Run: `& 'C:\Users\Administrator\.conda\envs\dayuwriter-control\python.exe' -m pytest tests/realsense/test_red_target.py -q`

Expected: FAIL because the new predicate parameter and reference-board helper do not exist.

- [ ] **Step 3: Implement the minimal filter**

Add an optional predicate to candidate selection. Derive the paper rectangle from the registered `ArucoBoardLayout` machine coordinates and map each candidate centre through the existing `predict_machine_xy` helper. Use the predicate only after `ReferenceStatus.state == 'ready'`.

- [ ] **Step 4: Verify focused tests and full suite**

Run: `& 'C:\Users\Administrator\.conda\envs\dayuwriter-control\python.exe' -m pytest tests/realsense/test_red_target.py tests/realsense/test_live_red_target_dashboard.py -q`

Run: `& 'C:\Users\Administrator\.conda\envs\dayuwriter-control\python.exe' -m pytest -q -p no:cacheprovider --basetemp "$env:USERPROFILE\pytest-temp\dayuwriter-tests"`

Expected: all tests pass.

- [ ] **Step 5: Commit and push**

```powershell
git add vision/realsense/red_target.py vision/realsense/live_red_target_dashboard.py tests/realsense/test_red_target.py tests/realsense/test_live_red_target_dashboard.py docs/superpowers
git commit -m "fix: filter red targets to reference board"
git push origin codex/dayuwriter-recovery-execution
```
