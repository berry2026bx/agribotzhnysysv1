# Live Red Target Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Display a fixed Camera A red marker's pixel, depth, camera XYZ, and calibrated P0 XY in a loopback browser dashboard without serial or GRBL access.

**Architecture:** A pure NumPy target module isolates red-marker segmentation and coordinate construction. A separate RealSense runtime module aligns frames and publishes snapshots through Python's standard-library HTTP server. The dashboard contains no machine-control code and binds only to `127.0.0.1`.

**Tech Stack:** Python 3.11, NumPy, pyrealsense2 2.58.3, standard-library `http.server`, pytest, browser HTML/JavaScript.

## Global Constraints

- Require Camera A serial `231122070403`.
- Use aligned depth-to-color and metric `depth_frame.get_distance()`.
- Map RGB pixel to P0 XY only through `camera-a-current-pose-result.json`.
- Bind the dashboard only to `127.0.0.1`.
- Do not import `serial` or `communication.dayuwriter`.
- Do not send GRBL, alter P0, or command any axis.

---

### Task 1: Pure Red Target Detection

**Files:**
- Create: `vision/realsense/red_target.py`
- Create: `tests/realsense/test_red_target.py`

**Interfaces:**
- Produces: `RedTarget`, `RedTargetConfig`, and `find_red_target(rgb, config) -> RedTarget | None`

- [ ] **Step 1: Write failing segmentation tests**

```python
rgb = np.zeros((80, 100, 3), dtype=np.uint8)
rgb[30:50, 40:60] = (255, 0, 0)
target = find_red_target(rgb)
assert target.center_uv == pytest.approx((49.5, 39.5))
```

- [ ] **Step 2: Verify the test fails because the module is missing**

Run: `python -m pytest tests/realsense/test_red_target.py -q`

- [ ] **Step 3: Implement thresholding, connected components, and candidate selection**

```python
mask = (red >= config.min_red) & ((red - green) >= config.min_red_advantage)
```

- [ ] **Step 4: Verify target tests pass**

Run: `python -m pytest tests/realsense/test_red_target.py -q`

### Task 2: Display-Only Coordinate Observation

**Files:**
- Modify: `vision/realsense/red_target.py`
- Modify: `tests/realsense/test_red_target.py`

**Interfaces:**
- Consumes: a `RedTarget`, depth frame, color intrinsics, RealSense deproject callable, and 3x3 pixel-to-machine matrix
- Produces: `TargetObservation` with `pixel_uv`, `depth_m`, `camera_xyz_m`, and `machine_xy_mm`

- [ ] **Step 1: Write failing observation tests**

```python
observation = observe_target(target, depth_frame, intrinsics, fake_deproject, matrix)
assert observation.machine_xy_mm == pytest.approx((30.0, 30.0))
```

- [ ] **Step 2: Implement valid-depth lookup and observation construction**

```python
u, v, depth_m = find_valid_depth_pixel(depth_frame, center=rounded_center, ...)
point = deproject(intrinsics, [u, v], depth_m)
```

- [ ] **Step 3: Verify target and observation tests pass**

Run: `python -m pytest tests/realsense/test_red_target.py -q`

### Task 3: Local Live Dashboard

**Files:**
- Create: `vision/realsense/live_red_target_dashboard.py`
- Modify: `tests/realsense/test_red_target.py`
- Create: `docs/dayuwriter/10-live-red-target-display.md`

**Interfaces:**
- Consumes: `--serial`, `--calibration`, `--port`, and `--min-area-px`
- Produces: `http://127.0.0.1:<port>/` with `/frame.bmp` and `/state.json`

- [ ] **Step 1: Write failing HTTP serialization tests**

```python
assert snapshot_state(observation)["state"] == "ready"
assert make_bmp_bytes(rgb).startswith(b"BM")
```

- [ ] **Step 2: Implement loopback server, BMP encoding, frame worker, and HTML page**

```python
server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
```

- [ ] **Step 3: Run static help and test suite**

Run: `python -m vision.realsense.live_red_target_dashboard --help`

Run: `python -m pytest tests/realsense -q`

### Task 4: Document and Commit

**Files:**
- Modify: `docs/dayuwriter/10-live-red-target-display.md`

- [ ] **Step 1: Document the red marker, local URL, ready state, and explicit no-motion boundary**

- [ ] **Step 2: Run the full non-GUI regression suite**

Run: `python -m pytest tests/realsense tests/dayuwriter/test_grbl_protocol.py tests/dayuwriter/test_grbl_controller.py tests/dayuwriter/test_grbl_jog.py tests/dayuwriter/test_workspace.py tests/dayuwriter/test_grbl_console.py tests/dayuwriter/test_grbl_diag.py -q`

- [ ] **Step 3: Commit and push**

```bash
git add vision/realsense tests/realsense docs/dayuwriter docs/superpowers
git commit -m "feat: add live red target display"
git push origin codex/dayuwriter-recovery-execution
```
