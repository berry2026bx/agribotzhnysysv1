# Camera A v3 Plane Calibration

## Accepted Display-Only Result

- Camera: Intel RealSense D435i A, serial `231122070403`.
- Capture method: direct `pyrealsense2` RGB-D acquisition, depth aligned to
  color, `640x480` at `30 fps`, with the first `90` frames discarded for
  exposure stabilization.
- Plane: the current fixed paper/machine/camera arrangement.
- Fit region: the `0-30 mm` square defined by `P0`, `X30Y0`, `X30Y30`, and
  `X0Y30`.
- Fit input: `camera-a-machine-reference-square-v3-input.json`.
- Result: `camera-a-machine-reference-square-v3-result.json`.

## Independent Validation

| Held-out physical point | Predicted XY (mm) | Error (mm) |
| --- | --- | --- |
| `(15, 15)` | `(15.195, 14.556)` | `0.485` |
| `(10, 20)` | `(9.747, 20.860)` | `0.896` |

The mean held-out error is `0.691 mm`; the maximum is `0.896 mm`.

## Scope

The v3 mapping may be used to display a detected red square's estimated
P0-relative XY coordinate inside the calibrated `0-30 mm` square. It is not
valid after moving the camera, paper, or machine reference, and it is not
evidence for the rest of the work area.

`motion_permission` remains `display_only`. The mapping does not authorize a
GRBL jog, unattended target following, probe use, or any Z-axis action.

## Rejected Records

The earlier `camera-a-machine-reference-square-result.json` is rejected: its
held-out error was `28.053 mm`. The later v2 record is also invalidated because
a fresh P0 capture after recovery shifted by about `75 px`, showing that the
previous pixel geometry did not describe the current physical arrangement.

## Runtime Notes

The previous loopback dashboard at port `8765` stopped its camera worker after
a frame timeout and retained an error page. Direct D435i capture remained
functional after a sufficient exposure warmup. Do not use the stale dashboard
page as a coordinate source; a fresh display process must load the v3 result.

The GRBL controller no longer reconfigures the serial port when its existing
write timeout already satisfies the remaining deadline. The regression suite
passed after that correction.
