# Live Red Target Display Design

## Goal

Show a live D435i A RGB frame in a local browser and, for one high-contrast red
circular marker resting on the calibrated paper plane, display its pixel,
aligned depth, camera XYZ, and predicted DayuWriter P0-XY coordinate.

## Scope Boundary

This feature is display-only. It has no `serial` import, no `COM4` access,
and no GRBL command path. A predicted coordinate is an observation for the
user to inspect, not permission to move the machine.

## Input Conditions

- Camera serial must equal `231122070403`.
- The camera and machine frame must retain the pose used by
  `camera-a-current-pose-result.json`.
- The target must be a saturated red, approximately circular marker lying on
  the same paper plane as the calibration points.
- The image must contain one candidate above the configured minimum area.

## Components

`red_target.py` contains pure NumPy color thresholding, connected-component
selection, overlay metadata, valid-depth lookup, and conversion from an RGB
pixel to a display-only observation. It is unit tested without hardware.

`live_red_target_dashboard.py` owns the RealSense pipeline. It locks the
requested serial, aligns depth to color, uses the color intrinsics with
`rs2_deproject_pixel_to_point`, and publishes the most recent RGB frame and
observation over a loopback-only HTTP server. The HTML page renders the image
and values locally in the browser.

## Data Flow

```text
D435i RGB + depth -> align depth to RGB -> red target center (u,v)
-> valid metric depth -> camera XYZ -> calibrated planar P0 XY
-> local browser display
```

The RGB-to-P0 mapping uses the existing `plane_mapping.py` matrix. Camera XYZ
is displayed in meters with the SDK convention `+X right`, `+Y down`, and
`+Z forward`. P0 XY is in mm.

## Error Handling

No red component, multiple unsuitable components, a depth hole, missing frame,
camera serial mismatch, invalid calibration artifact, or an invalid projection
must result in an explicit non-moving status. The image remains available when
the coordinate is unavailable.

## Verification

Synthetic RGB arrays test target selection and rejection. A fake depth frame
and fake deprojection function test metric camera XYZ and planar XY output.
Hardware verification requires one physical red marker on the paper plane and
an observed browser status with `state: ready`; it never moves the DayuWriter.
