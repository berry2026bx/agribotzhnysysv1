# RealSense D435i A Baseline Implementation Plan

> **For agentic workers:** Execute each task in order. The camera remains isolated from the GRBL serial controller throughout this plan.

**Goal:** Capture one reproducible, read-only RGB/depth/3D baseline from D435i camera A and save its device-specific metadata.

**Architecture:** A pure Python module validates the requested camera serial number and serializes a metric capture record. A thin CLI imports `pyrealsense2` only when run, starts one D435i with RGB and Z16 depth streams, aligns depth to color, samples the center color pixel, and writes JSON plus optional NumPy arrays. It never imports the DayuWriter controller or opens a COM port.

**Tech Stack:** Python 3.11, `pyrealsense2>=2.58`, NumPy 2.x, pytest 8.x, Intel RealSense D435i.

## Global Constraints

- Require `--serial`; do not select the first available camera.
- Use 640 x 480 at 30 fps: color RGB8 and depth Z16.
- Align depth to color before sampling a color pixel.
- Record every length in meters and label the camera coordinate convention: +X right, +Y down, +Z forward.
- Do not import, open, or command any GRBL/COM component.
- Reject zero, negative, NaN, and infinite depth instead of manufacturing a 3D point.
- Keep camera A artifacts under its serial number. Camera B requires an independent run and calibration record.

---

### Task 1: Define the Offline Contract

**Files:**
- Create: `tests/realsense/test_camera_probe.py`
- Create: `vision/__init__.py`
- Create: `vision/realsense/__init__.py`
- Create: `vision/realsense/camera_probe.py`

- [x] Add tests for: explicit serial parsing, center pixel selection, meter-labelled JSON output, and invalid-depth rejection.
- [x] Run the new test module before implementation. Observed: import failure because `vision.realsense.camera_probe` did not exist.
- [x] Implement only the pure validation and record-building functions necessary to make the tests pass.
- [x] Re-run the test module. Observed: 9 tests passed without a connected camera.

### Task 2: Connect the SDK to the Contract

**Files:**
- Modify: `vision/realsense/camera_probe.py`
- Modify: `environment/dayuwriter-control.yml`
- Modify: `docs/dayuwriter/README.md`

- [x] Add the serial-locked RealSense capture path with RGB8/Z16 streaming, depth-to-color alignment, metric center depth, color intrinsics, and `rs.rs2_deproject_pixel_to_point`.
- [x] Save JSON via `--output`; save `color.npy` and `depth.npy` only when `--save-frames` is supplied.
- [x] Run all offline tests. Observed: 105 tests passed using the environment's direct Python executable. `conda run` was not used for the final run because its GBK console forwarding crashed on a Unicode character.
- [x] Close RealSense Viewer, then run camera A once:

```powershell
conda run -n dayuwriter-control python -m vision.realsense.camera_probe `
  --serial 231122070403 `
  --output docs/dayuwriter/baseline/2026-07-27-realsense-camera-a-capture.json `
  --save-frames docs/dayuwriter/baseline/2026-07-27-realsense-camera-a-frames
```

- [x] Review the generated serial, stream profiles, depth scale, intrinsics, center pixel, center depth, and camera-frame point before starting physical mounting or P0 calibration.

### Task 3: Commit the Reproducible Baseline

**Files:**
- Modify: `docs/dayuwriter/baseline/2026-07-27-realsense-camera-a.md`
- Create: `docs/dayuwriter/baseline/2026-07-27-realsense-camera-a-capture.json`

- [x] Record whether the live capture succeeded, preserving the source JSON as the measurement record.
- [ ] Commit code, tests, manifest, plan, and the small JSON record. Do not commit raw image arrays by default.
