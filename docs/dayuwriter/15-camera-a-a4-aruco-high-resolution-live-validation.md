# Camera A A4 ArUco High-Resolution Live Validation

## Purpose

Record the first successful high-resolution, display-only live session after
the fixed A4 `a4-aruco-v3` reference board was registered to the new physical
P0. This record is evidence for camera acquisition and paper-plane mapping;
it does not authorize GRBL motion.

## Runtime Configuration

- Camera: Intel RealSense D435i A, serial `231122070403`.
- Python interpreter: `C:\Users\Administrator\.conda\envs\dayuwriter-control\python.exe`.
- RGB stream: `1280x720`, `rgb8`, 30 FPS.
- Depth stream: `640x480`, `z16`, 30 FPS, aligned to the RGB stream with
  `rs.align(rs.stream.color)`.
- Reference board: `a4-aruco-v3`, `DICT_4X4_50`, markers `0` through `5`.
- Registration artifact:
  `docs/dayuwriter/calibration/camera-a-a4-aruco-registration.json`.
- Dashboard command:

```powershell
& "C:\Users\Administrator\.conda\envs\dayuwriter-control\python.exe" -m vision.realsense.live_red_target_dashboard `
  --serial 231122070403 `
  --aruco-reference-board `
  --reference-registration docs/dayuwriter/calibration/camera-a-a4-aruco-registration.json `
  --port 8765
```

## Live Result

At `2026-07-28T14:57:33Z`, `http://127.0.0.1:8765/state.json` reported:

- Dashboard state: `ready`.
- Reference state: `ready`.
- Visible marker IDs: `0, 1, 2, 3, 4, 5`.
- Held-out marker validation: mean error `1.345 mm`, maximum error `2.348 mm`.
- Display-only limits: mean `<= 1.5 mm`, maximum `<= 3.0 mm`.
- Motion permission: `display_only`.

The browser also showed the current RGB image and all six board markers. The
dashboard has no serial-port, GRBL, jog, G-code, or motion control path.

## Important Interpretation Limit

The red region detected in this live frame was outside the physical A4 paper
area. Its projected machine value (`X=-41.50 mm`, `Y=286.07 mm`) is therefore
an extrapolation of the paper-plane homography, not a validated physical target
coordinate. It must not be used to command the writer.

For the next physical check, place one opaque red square or circle flat on the
printed A4 sheet, within the six-marker area, and compare its displayed
coordinate with a ruler measurement from P0. A red object on the pen, rail, or
any other height is not coplanar with the reference board and cannot be mapped
by this 2D paper-plane calibration.

## Software Change That Enabled This Session

The earlier `640x480` RGB path did not reliably detect all six obliquely viewed
markers. The dashboard now uses `1280x720` RGB while retaining `640x480` depth
aligned to RGB. ArUco detection also prefers OpenCV's current
`cv2.aruco.ArucoDetector` API, with a fallback to the legacy interface for
older OpenCV versions. The complete test suite passed with `151 passed` after
this change.
