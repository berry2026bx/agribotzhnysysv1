# YOLO Object-to-DayuWriter Demonstration Design

## Goal

Add a first YOLO demonstration path that detects a selected COCO object with a pretrained Ultralytics model, displays class/confidence/pixel/depth/camera-XYZ/machine-XY data in the existing D435i dashboard, and optionally executes one supervised XY move followed by a small Z drop, a 10-second hold, and a return to the fixed physical P0. The design must also leave a clean adapter boundary for a later custom weed model.

## Evidence and current constraints

- The existing dashboard is display-only and already owns D435i frame acquisition, RGB/depth alignment, ArUco reference tracking, red-target display, and `/state.json`.
- The existing plane mapping is valid only for the fixed camera pose and for points on the calibrated paper plane. It is not sufficient by itself for elevated objects because perspective causes a pixel-to-plane error.
- `communication.dayuwriter.visual_follow` already validates `state=ready`, `mapping_state=available`, `motion_permission=display_only`, a fixed P0 baseline, stable target samples, bounded XY movement, optional bounded Z movement, and return-to-P0 behavior.
- The installed `dayuwriter-control` environment has NumPy 2.4.6, pyrealsense2 2.58.3, and OpenCV contrib 4.13.0, but it does not currently have `torch` or `ultralytics`.
- The current computer has an NVIDIA GeForce RTX 3060 with 12 GB VRAM and NVIDIA driver 595.71 (`nvidia-smi` reports CUDA capability 13.2). It is suitable for the small pretrained YOLO demonstration model. The PyTorch wheel's bundled CUDA runtime version, not the `nvidia-smi` CUDA capability string, determines the exact supported installation command.
- Ultralytics documentation describes Python inference through `YOLO(...); results = model.predict(...); result.boxes.xyxy/conf/cls`, and states that the package/models are AGPL-3.0 or Enterprise licensed. This repository is for research/education; licensing must be reviewed before redistribution or closed-source deployment.
- The first real-machine run must remain supervised. A dashboard label or a successful model inference is not evidence that a physical path is clear.

## Scope

### In scope

1. A detector adapter with an Ultralytics implementation and a deterministic fake implementation for tests.
2. A configurable model path, confidence threshold, target class allow-list, and maximum detections.
3. A YOLO dashboard mode that annotates the live RGB frame and publishes one selected target in JSON.
4. Target localization using the D435i depth frame at the detection-box center with a finite-neighbor fallback.
5. A camera-to-machine 3D transform derived from the ArUco reference board pose, with the target point projected onto the writer XY plane for the XY move and a separately reported height.
6. Reuse of the existing P0-anchored supervised follow executor; it automatically discovers the one connected CH340 port after the operator explicitly arms a session, and introduces no new serial protocol.
7. Offline/unit tests for detection parsing, target selection, finite-depth handling, 3D transform math, dashboard schema, and motion gating.
8. Runbook updates explaining how to install the optional YOLO dependencies, download a pretrained model, run display-only mode, then explicitly arm supervised motion.

### Out of scope

- Training a weed model in this change.
- Grasping, suction, or other end effectors.
- Automatic homing, limit switches, encoder feedback, or recovery after a lost step.
- Unbounded speed or workspace.
- Autonomous operation without the operator physically observing the machine.
- Treating an arbitrary object center as a safe contact point.

## Coordinate and motion convention

The source of truth for the machine origin remains the physically confirmed P0. The YOLO box center is only an image measurement. For each accepted detection:

```text
RGB box center (u,v)
  -> aligned depth sample z_camera
  -> RealSense deprojection (x_camera,y_camera,z_camera)
  -> board-pose transform (x_board,y_board,z_board)
  -> writer coordinates (x_machine,y_machine,z_height)
  -> XY delta = target_machine_xy - commanded_machine_xy
```

The ArUco board pose is estimated from the known board geometry and the current color intrinsics. The transform must be recomputed when the camera, paper, board, or writer is moved. The existing planar homography remains available as a display-only fallback for a confirmed paper-plane target, but it must not silently replace the 3D path for an elevated object.

The first demo uses a target anchor named `center`. The code must expose this explicitly because the center of a bottle bounding box is not its base/contact point. The default motion policy is `xy_to_target_then_z_drop`; it does not claim to place the pen at the object's physical bottom.

## Components

### 1. Detector adapter

Create `vision/yolo/detector.py` with:

- `Detection(class_id: int, class_name: str, confidence: float, xyxy: tuple[float, float, float, float])`
- `DetectorConfig(model_path: str, confidence: float = 0.5, classes: frozenset[str] | None = None, max_detections: int = 20)`
- `YoloDetector.predict(rgb: np.ndarray) -> tuple[Detection, ...]`
- `select_target(detections, requested_class: str) -> Detection | None`

The adapter imports Ultralytics lazily so the existing red-target and GRBL tests remain runnable without Torch. It converts tensors to plain finite Python values, clips/rejects invalid boxes, filters classes and confidence, and sorts deterministically by confidence descending then area descending.

### 2. 3D localization

Create `vision/realsense/object_localization.py` with a pure transform/data API:

- `CameraPoint(x_mm, y_mm, z_mm)`
- `MachinePoint(x_mm, y_mm, z_mm)`
- `estimate_depth_m(depth_frame, u, v, radius) -> float`
- `deproject_color_pixel(color_intrinsics, depth_m, (u,v), deproject) -> CameraPoint`
- `transform_camera_to_machine(camera_point, rotation, translation) -> MachinePoint`
- `project_target_to_writer_plane(machine_point, plane_z_mm) -> MachinePoint`

Depth is sampled from a small odd-sized neighborhood and must be finite, positive, and sufficiently populated. The transform uses millimetres internally after deprojection. The returned `z_height_mm` is displayed and checked, but is not automatically used for a large Z move.

### 3. ArUco pose

Extend `vision/realsense/aruco_plane_calibration.py` or add `aruco_pose.py` to estimate the board pose from the same six detected IDs and the known board corner coordinates. Use `cv2.solvePnP`/`solvePnPRansac` with the color camera intrinsics and distortion coefficients. Reject incomplete IDs, non-finite pose, reprojection error above the existing validation limit, or board motion. Persist a pose record that includes camera serial, stream size, board revision, capture time, rotation/translation, and error metrics.

### 4. Dashboard mode

Add a separate `vision/realsense/live_yolo_dashboard.py` rather than changing the red-target endpoint semantics. It reuses the camera worker lifecycle and board registration checks, exposes:

- `/` HTML page
- `/frame.bmp` annotated RGB frame
- `/state.json` machine-readable snapshot

The snapshot contains `state`, `motion_permission`, `camera.serial`, `target.class_name`, `target.confidence`, `target.pixel_center_uv`, `target.camera_xyz_mm`, `target.machine_xyz_mm`, `target.machine_xy_mm`, `mapping_state`, `reference_state`, `pose_validation`, and `error`. When detection/depth/reference is invalid, the frame remains visible but the target coordinate fields are omitted and `motion_permission` stays `display_only`.

### 5. Motion integration

Do not let the dashboard itself open a serial port. The desktop launcher may automatically discover exactly one CH340 port and start the separate follow executor only after the operator explicitly arms a session. Extend the existing follow parser to accept a generic target record only when:

- the requested class matches;
- `state=ready`;
- `mapping_state=available`;
- the reference board is stable;
- the target has three stable samples within the existing spread threshold;
- P0 is the fixed physical baseline;
- the target is inside the measured machine envelope;
- `--execute` and `--physical-preflight` are both present;
- exactly one CH340 port is discovered and reported by the launcher.

The follow executor sends XY first, optionally sends a configured `z_drop_mm` no larger than 1 mm, waits 10 seconds, and returns XY to P0. The default command remains display-only.

## CLI and user workflow

1. The operator installs optional inference dependencies in `dayuwriter-control`; the project must never try to install them automatically. For the RTX 3060 computer, open the official [PyTorch Get Started page](https://pytorch.org/get-started/locally/), select Stable / Windows / Pip / Python / CUDA, and copy the command that page generates for the current supported CUDA wheel. Then run `python -m pip install ultralytics`. A separately installed CUDA Toolkit is not required for standard PyTorch pip wheels.
2. Place a pretrained model such as `yolo11n.pt` or the currently supported small detection model in a user-owned models directory. The first Ultralytics load may download the weight file.
3. Start the YOLO dashboard with a serial number, model path, class name, ArUco registration, and a non-motion port.
4. Verify the page shows the expected class, confidence, pixel center, finite camera XYZ, machine XY, and a valid reference state.
5. Run a preview command that prints the proposed delta without a COM port.
6. In the desktop launcher, confirm the physical-P0 and path-clear checklist, then choose `Start YOLO automatic follow`. The launcher discovers the sole CH340 port, opens it in the separate executor, and runs the same target / 10-second hold / P0-return cycle automatically.
7. Inspect the physical result and the `/state.json`/terminal log. The launcher must provide a `Stop automatic follow` control; stopping can leave the pen away from P0, so P0 must be physically re-confirmed before the next run.

The exact commands belong in the implementation runbook after the CLI names and options are implemented.

## Error handling

- Missing `ultralytics`/Torch: dashboard reports `yolo_dependency_missing`; no camera motion is attempted.
- Model load or inference error: retain the RGB frame, publish error, omit target coordinates, and stop accepting motion.
- Zero/invalid depth: publish detection without XYZ, set `depth_state=invalid`, and do not move.
- ArUco loss/motion: invalidate the matrix immediately; do not reuse a stale pose for motion.
- Multiple detections: select only the requested class and highest-confidence valid target; otherwise require explicit target selection.
- Camera runtime/USB failure: release the pipeline and preserve the original error.
- GRBL error or timeout: stop the current cycle and report that the physical P0 must be re-confirmed before another run.

## Testing and acceptance

Before real hardware execution, tests must cover:

- conversion of an Ultralytics-like result to finite `Detection` records;
- confidence/class filtering and deterministic target selection;
- invalid bounding boxes;
- median finite-depth sampling and zero-depth rejection;
- known camera-to-machine transform and plane projection;
- dashboard JSON omission on invalid depth/reference;
- motion parser rejection when YOLO state is not ready;
- fixed P0 baseline (a first target can never become P0);
- preview has no serial side effect;
- execution requires explicit preflight and uses the existing controller.

The physical acceptance sequence is intentionally separate:

1. Dashboard display-only with no 12 V motor power.
2. One stationary object on the paper plane.
3. Confirm displayed class and coordinates against a ruler.
4. One small XY move with pen tip hovering.
5. Optional 0.5-1.0 mm Z demonstration only after XY is correct.
6. Confirm 10-second hold and return to physical P0.

## Licensing note

Ultralytics documents its open-source package and models under AGPL-3.0 with an Enterprise option. For a personal academic demonstration, keep the model and source use compliant with the applicable license and document the model/version. Before distributing a closed-source product or internal commercial tool, obtain legal review and the appropriate license.

## Alternatives considered

### A. Reuse the red-target dashboard and replace the segmentation function
Smallest code change, but it preserves a misleading planar assumption and cannot represent class/confidence/3D target semantics cleanly. Rejected for the main path.

### B. Add YOLO as an optional detector adapter and a separate dashboard
Slightly more code, but isolates model dependencies, preserves the working red-target path, supports fake tests, and makes later weed-model replacement straightforward. Recommended.

### C. Put YOLO and serial control in one process
Fewer processes, but a model or camera failure could own the serial port and make recovery harder. Rejected; keep dashboard and motion executor separate.

## Open operator decision

For the first physical demo, choose the target class and anchor policy:

- Recommended: `bottle` on the paper plane, move to the box center's projected XY, and perform no Z drop until the center-vs-base limitation is demonstrated.
- Alternative: `cup` or `book`, with the same policy.
- A later object-height demo may add a measured base-point or segmentation anchor, but it is not part of this first implementation.
