# A4 ArUco Reference Board and Automatic Display Calibration

## Goal

Replace temporary, manually observed red-square calibration with a reusable camera-A workflow. The operator may transport the DayuWriter or re-mount the D435i A. Once the reference board remains fixed relative to the writer's P0 frame and is visible, the software must recover the current RGB-pixel to machine-XY plane mapping automatically. It must remain display-only.

This design addresses planar targets on the reference board's plane. It does not yet provide automatic motion, target following, Z control, weed detection, or a 3D camera-to-machine transform for targets above the plane.

## Facts and Boundaries

- Camera: Intel RealSense D435i A, serial `231122070403`.
- Camera stream: aligned `640 x 480`, RGB plus depth, at 30 FPS.
- The existing v3 result is a valid historical display-only result for one camera pose, with two held-out point errors of 0.485 mm and 0.896 mm. It is not a permanent calibration and is not overwritten by this feature.
- P0 is a manual physical reference, not homing or encoder truth.
- GRBL remains outside the new module and UI. `motion_permission` is always `display_only`.

## Physical Reference Board

The board is one landscape A4 sheet (`297 x 210 mm`) mounted on a rigid, flat backing. It lies on the same plane as the intended planar targets; it is not attached underneath the machine or left as a loose sheet.

The printable board uses OpenCV `DICT_4X4_50`, board revision `a4-aruco-v1`, and six 40 mm square markers. IDs and marker-center board coordinates are:

| ID | Location | Board X (mm) | Board Y (mm) |
| --- | --- | ---: | ---: |
| 0 | upper-left | 25 | 25 |
| 1 | upper-right | 272 | 25 |
| 2 | right-center | 272 | 105 |
| 3 | lower-right | 272 | 185 |
| 4 | lower-left | 25 | 185 |
| 5 | left-center | 25 | 105 |

The printed center is board P0 at `(148.5, 105.0) mm`, with visible X+ and Y+ arrows. The marker ring leaves the central area clear for the target. The generator also renders a 100 mm scale bar, board revision, dictionary, and marker IDs. The operator prints at 100% scale and measures the scale bar before use.

The reference board is registered to the writer exactly once after a new installation or after it has moved relative to the writer:

1. Mechanically align the pen tip to the printed P0 cross.
2. Check the printed X+ and Y+ reference crosses using known bounded 30 mm machine jogs from P0.
3. Physically secure the board only after all three alignments are correct.
4. Record the operator confirmation and board revision in the registration artifact.

Moving the entire writer with this secured board preserves the board-to-P0 relationship. Re-mounting the camera does not require this registration. Moving the board, changing its height or tilt, or redefining P0 does.

## Calibration Session

The calibration UI starts a camera-A display-only session as follows:

1. Verify the exact camera serial and fixed stream configuration.
2. Discard 90 startup frames for RGB exposure and white-balance settling.
3. Detect six ArUco markers across 12 valid frames and median their image corners.
4. Fit a homography from corner pixels of IDs 0, 1, 3, and 4 to their known machine-plane coordinates.
5. Validate against all corners of held-out IDs 2 and 5.
6. Accept the session only when every required marker is detected and the held-out mean error is at most 1.5 mm and maximum error is at most 3.0 mm.
7. Save an immutable display-only session artifact containing camera serial, stream configuration, board revision, timestamp, matrix, point data, and validation metrics.

These limits are an initial display-only quality gate, not an accuracy claim. The UI reports measured errors and rejects sessions outside the limits.

## Runtime Display and Safety

The existing loopback-only dashboard is extended rather than given GRBL access. It shows the RGB image, red-target overlay, detected reference-marker overlay, camera XYZ, predicted machine XY, current board/session state, and validation metrics.

Each live frame checks the visible reference markers. The mapping is available only when at least the required fit and validation markers are visible and the quality gate passes. If the camera moves, the fresh marker observations update the display transform. If markers are obscured, insufficient, or fail the quality gate, state becomes `reference_lost` or `calibration_rejected` and no machine XY is displayed as valid.

The page has no motion endpoint, button, serial-port field, or import of the GRBL controller. A later, separate design and validation stage is required before a human-confirmed single XY movement can consume this output.

## Components

- `vision/realsense/aruco_reference_board.py`: board layout metadata and a deterministic printable A4 artifact generator.
- `vision/realsense/aruco_plane_calibration.py`: marker correspondence collection, homography fit, held-out validation, artifact serialization, and runtime quality checks.
- `vision/realsense/live_red_target_dashboard.py`: display-only marker status and camera-to-machine mapping integration.
- `docs/dayuwriter/calibration/`: immutable registration and per-session camera-A records. Camera B is out of scope.
- `tests/dayuwriter/`: offline synthetic-corner tests for layout, fitting, validation failure, and display-only contract.

`opencv-contrib-python` is added explicitly because the ArUco APIs are not part of the base OpenCV package. It is installed only in the existing `dayuwriter-control` environment during implementation.

## Validation

Automated tests must cover:

- board dimensions, IDs, non-overlapping marker positions, and known P0;
- recovery of a synthetic projective mapping from fit markers;
- rejection for a missing marker, serial mismatch, non-finite data, excessive held-out error, or changed stream resolution;
- the no-GRBL display-only contract.

The physical acceptance procedure is:

1. Register the fixed reference board to P0 once.
2. Position the red square at two known held-out positions in the central region.
3. Compare displayed XY with the physical marks and record measured errors.
4. Re-mount the camera without moving the board, repeat step 3, and retain a separate session artifact.

No motion validation is part of this feature.

## Sources

- OpenCV's ChArUco and ArUco FAQ documents that ChArUco combines chessboard patterns with ArUco markers and that ArUco boards allow more flexible layouts:
  https://docs.opencv.org/4.13.0/d1/dcb/tutorial_aruco_faq.html
- OpenCV documents detection of ChArUco identifiers/corners and local homography refinement:
  https://docs.opencv.org/4.13.0/d9/df5/classcv_1_1aruco_1_1CharucoDetector.html
- RealSense documents depth-to-color alignment and metric depth use. It does not provide the camera-to-machine plane transformation:
  https://github.com/realsenseai/librealsense/blob/master/wrappers/python/examples/align-depth2color.py
