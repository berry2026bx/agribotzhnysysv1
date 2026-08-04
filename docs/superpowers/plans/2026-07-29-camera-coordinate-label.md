# Camera Coordinate Label Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the live image coordinate label without changing its position, content, or visibility rules.

**Architecture:** Keep the existing `target-label` DOM element and JavaScript positioning. Change only its CSS contract from an opaque dark rectangle to a translucent white annotation with a red border and dark readable text.

**Tech Stack:** Python inline HTML/CSS/JavaScript, pytest, local browser verification.

## Global Constraints

- Preserve `motion_permission=display_only`.
- Do not modify target detection, coordinate mapping, or GRBL code.
- The label must stay hidden when target detection or mapping is unavailable.

---

### Task 1: Restyle The Camera Label

**Files:**
- Modify: `vision/realsense/live_red_target_dashboard.py`
- Test: `tests/realsense/test_live_red_target_dashboard.py`

**Interfaces:**
- Preserves DOM id `target-label` and its existing dynamic text/position code.
- Adds a CSS contract for the approved translucent white/red/dark-gray treatment.

- [x] **Step 1: Write the failing page-contract test**

```python
def test_dashboard_page_styles_target_label_as_translucent_annotation() -> None:
    page = _html_page()
    assert '#target-label{position:absolute' in page
    assert 'background:rgba(255,255,255,.88)' in page
    assert 'border:1px solid #d61f26' in page
    assert 'color:#303833' in page
```

- [x] **Step 2: Verify failure**

```powershell
& "C:\Users\Administrator\.conda\envs\dayuwriter-control\python.exe" -m pytest -q tests\realsense\test_live_red_target_dashboard.py
```

Expected: the target-label CSS assertions fail because the existing label has
an opaque dark background and white text.

- [x] **Step 3: Write minimal implementation**

Replace only the `#target-label` CSS rule with the approved semi-transparent
white background, thin red border, dark gray text, and a subtle shadow.

- [x] **Step 4: Verify page and browser output**

Run the focused test and the full pytest suite. Restart the display-only
dashboard, reload `http://127.0.0.1:8765/`, and verify the label in the live
camera image remains offset from the red target box.

- [x] **Step 5: Commit**

```powershell
git add vision/realsense/live_red_target_dashboard.py tests/realsense/test_live_red_target_dashboard.py docs/superpowers
git commit -m "style: refine camera coordinate label"
```
