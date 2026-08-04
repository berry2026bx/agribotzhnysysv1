# Camera A Plane Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a display-only, tested pixel-to-DayuWriter-XY mapping CLI for one fixed D435i A pose.

**Architecture:** `plane_mapping.py` is a pure NumPy module that validates observations, solves an 8-parameter pixel-to-machine homography, predicts XY, and writes a JSON artifact.  The CLI consumes a versioned JSON input and never imports the DayuWriter serial-control package.

**Tech Stack:** Python 3.11, NumPy, pytest.

## Global Constraints

- Require Camera A serial `231122070403` in the current calibration input.
- Fit points and validation points must remain separate.
- The artifact must set `motion_permission` to `display_only`.
- Do not import `serial`, `communication.dayuwriter`, or send a GRBL command.

---

### Task 1: Homography Core

**Files:**
- Create: `vision/realsense/plane_mapping.py`
- Test: `tests/realsense/test_plane_mapping.py`

**Interfaces:**
- Consumes: `CalibrationPoint(id: str, pixel_uv: tuple[float, float], machine_xy_mm: tuple[float, float])`
- Produces: `fit_pixel_to_machine(points) -> numpy.ndarray` and `predict_machine_xy(matrix, pixel_uv) -> tuple[float, float]`

- [ ] **Step 1: Write failing tests**

```python
matrix = fit_pixel_to_machine(points)
assert predict_machine_xy(matrix, held_out_pixel) == pytest.approx(held_out_xy)
```

- [ ] **Step 2: Verify tests fail because `plane_mapping` is missing**

Run: `python -m pytest tests/realsense/test_plane_mapping.py -q`

- [ ] **Step 3: Implement validation, least-squares homography solving, and projection**

```python
solution, _, rank, _ = np.linalg.lstsq(system, expected, rcond=None)
if rank < 8:
    raise PlaneMappingError("fit points are degenerate")
```

- [ ] **Step 4: Verify core tests pass**

Run: `python -m pytest tests/realsense/test_plane_mapping.py -q`

### Task 2: Artifact and CLI

**Files:**
- Modify: `vision/realsense/plane_mapping.py`
- Modify: `tests/realsense/test_plane_mapping.py`

**Interfaces:**
- Consumes: JSON with `camera.serial`, `fit_points`, and `validation_points`
- Produces: JSON with `matrix_pixel_to_machine`, residual statistics, and `motion_permission: "display_only"`

- [ ] **Step 1: Write failing artifact test**

```python
record = build_calibration_record("231122070403", fit_points, validation_points)
assert record["motion_permission"] == "display_only"
```

- [ ] **Step 2: Implement JSON parsing, residual metrics, and file output**

```python
errors = [validation_error_mm(matrix, point) for point in validation_points]
```

- [ ] **Step 3: Verify all mapping tests pass**

Run: `python -m pytest tests/realsense/test_plane_mapping.py -q`

### Task 3: Current Camera A Artifact and Regression Suite

**Files:**
- Create: `docs/dayuwriter/calibration/camera-a-current-pose-input.json`
- Create: `docs/dayuwriter/calibration/camera-a-current-pose-result.json`
- Modify: `docs/dayuwriter/06-d435i-vision-roadmap.md`

- [ ] **Step 1: Record the four current-pose fit observations and the independent center observation**

Use the confirmed coordinates `(0,0)`, `(60,0)`, `(60,60)`, `(0,60)`, and held-out `(30,30)`.

- [ ] **Step 2: Run CLI and inspect the nonzero held-out residual**

Run: `python -m vision.realsense.plane_mapping --input docs/dayuwriter/calibration/camera-a-current-pose-input.json --output docs/dayuwriter/calibration/camera-a-current-pose-result.json`

- [ ] **Step 3: Run the complete suite and commit**

Run: `python -m pytest -q -p no:cacheprovider --basetemp "$env:USERPROFILE\\pytest-temp\\dayuwriter-tests"`
