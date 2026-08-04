# YOLO Object-to-DayuWriter Implementation Plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox syntax.

Goal: add a pretrained Ultralytics YOLO demonstration that reports class, confidence, pixel position, RealSense camera XYZ, and fixed-P0 machine XY, then performs a supervised bounded XY move, optional small Z drop, ten-second hold, and return to P0.

Architecture: preserve the existing red-target dashboard and GRBL follow path. Add a lazy detector adapter, pure depth/transform utilities, an ArUco solvePnP pose record, and a separate YOLO dashboard. The dashboard remains display-only and never owns a serial port; a separate launcher/follow executor consumes validated state only after explicit physical preflight.

Tech stack: Python 3.11, NumPy, pyrealsense2, OpenCV contrib/ArUco, Ultralytics, PyTorch CUDA wheel, existing pyserial/GRBL modules, pytest, PowerShell/CMD launchers.

## Global Constraints

- Preserve opencv-contrib-python; do not install ordinary opencv-python over it.
- Import Ultralytics lazily so existing camera/GRBL tests run without Torch.
- Physical P0 remains the only origin; the first YOLO target can never become P0.
- Dashboard default is motion_permission=display_only; no implicit serial open or movement.
- Real motion requires execute, physical-preflight, ready state, stable ArUco reference, stable target samples, finite depth, bounded workspace coordinates, and exactly one CH340.
- Default demonstration sends XY only, holds ten seconds, and returns to P0; Z drop defaults to zero and is capped at 1.0 mm.
- Recompute board pose and mapping whenever camera, paper, reference board, or writer placement changes.
- Never remove workspace/speed bounds or bypass physical clearance checks.
- Do not commit existing user/field files unrelated to this plan.

---

### Task 1: Dependency and operator prerequisites

Files: environment/dayuwriter-control.yml; docs/dayuwriter/32-yolo-dependencies-and-first-run.md; tests/dayuwriter/test_yolo_runbook_paths.py

Steps:
- [ ] Write a failing test asserting that the runbook names dayuwriter-control, preserves OpenCV contrib, gives the model path convention, and states display-only before motion.
- [ ] Run python -m pytest -q tests/dayuwriter/test_yolo_runbook_paths.py and verify failure because the runbook is absent.
- [ ] Add optional dependency notes and commands: use the official PyTorch selector for the current supported CUDA wheel, then python -m pip install ultralytics; document verification and first model download. Do not add mandatory Torch to the base environment file.
- [ ] Run the focused test and verify pass.
- [ ] Commit with git add environment/dayuwriter-control.yml docs/dayuwriter/32-yolo-dependencies-and-first-run.md tests/dayuwriter/test_yolo_runbook_paths.py; git commit -m docs: add yolo dependency and first-run guide.

### Task 2: Detector adapter

Files: vision/yolo/__init__.py; vision/yolo/detector.py; tests/vision/yolo/test_detector.py

Interfaces: Detection(class_id, class_name, confidence, xyxy); DetectorConfig(model_path, confidence=0.5, classes=None, max_detections=20); YoloDetector.predict(rgb); select_target(detections, requested_class).

Steps:
- [ ] Write failing tests for finite conversion from an Ultralytics-like result, confidence/class filtering, invalid boxes, deterministic ordering, and requested-class selection without importing Ultralytics.
- [ ] Run the focused test and verify failure.
- [ ] Implement lazy import, tensor normalization, image-bound clipping, finite/positive-area validation, and confidence/area sorting.
- [ ] Run the focused test and verify pass without loading a real model.
- [ ] Commit with git add vision/yolo tests/vision/yolo; git commit -m feat: add lazy yolo detector adapter.

### Task 3: RealSense depth and transform math

Files: vision/realsense/object_localization.py; tests/realsense/test_object_localization.py

Interfaces: CameraPoint; MachinePoint; estimate_depth_m(depth_frame, u, v, radius=2); deproject_color_pixel(color_intrinsics, depth_m, uv, deproject); transform_camera_to_machine(camera_point, rotation, translation); project_target_to_writer_plane(machine_point, plane_z_mm).

Steps:
- [ ] Write failing synthetic tests with zero, NaN, and finite depth neighbors; assert median selection, zero rejection, known rotation/translation, and plane projection.
- [ ] Run the focused test and verify failure.
- [ ] Implement finite-positive depth checks, injected deprojection, R times p plus t, millimetre units, and height separate from XY projection.
- [ ] Run the focused test and verify pass.
- [ ] Commit with git add vision/realsense/object_localization.py tests/realsense/test_object_localization.py; git commit -m feat: add robust object depth localization.

### Task 4: Six-marker ArUco board pose

Files: vision/realsense/aruco_pose.py; vision/realsense/aruco_plane_calibration.py; tests/realsense/test_aruco_pose.py

Interfaces: BoardPose(rotation, translation, reprojection_error_px, visible_ids, serial, stream_size); estimate_board_pose(corners_by_id, camera_matrix, dist_coeffs, board_geometry, serial, stream_size); validate_board_pose(pose, previous_pose=None, max_error_px=...).

Steps:
- [ ] Write synthetic projection and rejection tests for missing IDs, non-finite pose, and excessive reprojection error.
- [ ] Run the focused test and verify failure.
- [ ] Implement solvePnP or solvePnPRansac using existing six-ID geometry and current color intrinsics/distortion; persist serial, stream size, board revision, timestamp, pose vectors, IDs, and error metrics.
- [ ] Run the focused test and verify pass.
- [ ] Commit with git add vision/realsense/aruco_pose.py vision/realsense/aruco_plane_calibration.py tests/realsense/test_aruco_pose.py; git commit -m feat: add validated aruco board pose.

### Task 5: Display-only YOLO dashboard

Files: vision/realsense/live_yolo_dashboard.py; tests/realsense/test_live_yolo_dashboard.py

Interfaces: CLI options serial, model, class-name, confidence, host, port, motion-permission; endpoints /, /frame.bmp, /state.json; state fields state, motion_permission, camera.serial, target class/confidence/pixel center/camera XYZ/machine XYZ/machine XY, mapping_state, reference_state, pose_validation, error.

Steps:
- [ ] Write schema and lifecycle tests with fake camera, detector, and pose providers. Assert valid fields, invalid-depth omission, missing-dependency error, and frame availability.
- [ ] Run the focused test and verify failure.
- [ ] Implement camera worker and HTTP endpoints by reusing existing lifecycle patterns. Annotate class/confidence and a white translucent coordinate label to the right of the red detection box; hide it when coordinates are invalid. Never open serial here.
- [ ] Run focused and existing realsense tests and verify pass.
- [ ] Commit with git add vision/realsense/live_yolo_dashboard.py tests/realsense/test_live_yolo_dashboard.py; git commit -m feat: add display-only yolo realsense dashboard.

### Task 6: Fixed-P0 follow integration

Files: communication/dayuwriter/visual_follow.py; tests/dayuwriter/test_visual_follow_yolo_state.py

Steps:
- [ ] Write failing tests for class mismatch, stale reference, missing depth, unstable samples, non-ready state, first-target-as-P0, unbounded coordinates, preview without serial side effect, and execution requiring both explicit flags.
- [ ] Run the focused test and verify failure.
- [ ] Extend LiveTarget and parse_live_target compatibly; keep fixed P0, compute commanded delta, send XY first, cap Z drop at 1.0 mm, hold ten seconds, return to P0, and require physical re-confirmation after GRBL errors.
- [ ] Run focused and existing dayuwriter tests and verify pass.
- [ ] Commit with git add communication/dayuwriter/visual_follow.py tests/dayuwriter/test_visual_follow_yolo_state.py; git commit -m feat: gate yolo targets through fixed p0 follow.

### Task 7: Explicit launcher, stop control, and runbook

Files: communication/dayuwriter/simple_launcher.py; scripts/start_dayuwriter_yolo.ps1; scripts/start_dayuwriter_yolo.cmd; scripts/stop_dayuwriter_yolo.ps1; docs/dayuwriter/33-yolo-display-and-supervised-motion.md; tests/dayuwriter/test_yolo_launcher.py

Steps:
- [ ] Write failing tests for zero or multiple CH340 rejection, display-only startup, explicit arm requirement, PID file creation, and stop cleanup.
- [ ] Run the focused test and verify failure.
- [ ] Implement narrow launcher and scripts. Keep dashboard and serial ownership separate. Require physical checklist before execute plus physical-preflight. Record command, serial, model, start time, and stop reason.
- [ ] Run focused tests and git diff --check.
- [ ] Commit all Task 7 files with git commit -m feat: add supervised yolo launcher and stop control.

### Task 8: Offline acceptance and staged hardware verification

Files: docs/dayuwriter/33-yolo-display-and-supervised-motion.md only for verified command corrections; all new YOLO tests.

Steps:
- [ ] Run python -m pytest -q -p no:cacheprovider --basetemp \$env:USERPROFILE\\pytest-temp\\dayuwriter-yolo-tests. No test may open a real COM port.
- [ ] With 12 V disconnected and Viewer closed, run display-only. Confirm six ArUco IDs, finite depth, target class/confidence, camera XYZ, machine XY, and display_only.
- [ ] Compare two stationary paper-plane points with a ruler; if inaccurate, redo camera/board/P0 registration instead of changing GRBL coordinates.
- [ ] With 12 V connected, pen hovering, path clear, fixed physical P0 confirmed, and one CH340 present, arm one XY run. Confirm target, ten-second hold, and return to P0.
- [ ] Add optional 0.5 to 1.0 mm Z only after XY passes and re-check clearance.
- [ ] Commit only verified runbook corrections.

## Self-Review

- [ ] Detector, depth math, board pose, dashboard, motion gates, launcher, stop behavior, tests, and runbook each have a concrete task.
- [ ] No task changes fixed P0 or removes limits.
- [ ] No task installs Torch or Ultralytics automatically.
- [ ] Existing uncommitted field files remain untouched.

## Execution Handoff

Plan complete and saved to docs/superpowers/plans/2026-08-04-yolo-object-to-dayuwriter.md. Choose subagent-driven implementation with review after each task, or inline implementation in this session with checkpoints.

