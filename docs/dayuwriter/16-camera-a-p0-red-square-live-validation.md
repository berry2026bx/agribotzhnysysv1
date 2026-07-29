# Camera A P0 Red Square Live Validation

## Physical Setup

- D435i A serial: `231122070403`.
- The non-reflective red square is approximately `10 mm x 10 mm`, flat on the
  printed A4 reference sheet.
- The square was placed with its geometric center at the manually marked P0.
- The writer and camera were not moved during this check.

## Software State

The display-only dashboard was restarted after a stale worker reported a
temporary RealSense disconnect. SDK enumeration then confirmed the camera as
`RealSense D435I`, serial `231122070403`, USB `3.2`.

The live tracker now uses OpenCV ArUco subpixel corner refinement. After a
12-frame session passes validation, it holds that mapping instead of refitting
on every frame. It invalidates the session only when a marker corner moves more
than 8 RGB pixels or a required marker disappears. The 8-pixel threshold is
based on a stationary 180-frame sample: p50 drift `0.38 px`, p90 `1.37 px`,
p95 `3.51 px`, p99 `5.58 px`, maximum `8.87 px`.

## Observed Result

At `2026-07-29T07:18:20Z`, the state endpoint reported:

- Dashboard state: `ready`.
- Reference state: `ready`.
- Visible marker IDs: `0, 1, 2, 3, 4, 5`.
- Held-out marker validation: mean `1.472 mm`, maximum `2.175 mm`.
- Red target depth: approximately `0.419 m`.
- Red target machine-plane estimate: approximately `X=2.03 mm`, `Y=0.08 mm`.
- Across eight samples, the estimate was approximately `X=1.99..2.14 mm`,
  `Y=-0.00..0.12 mm`.
- Motion permission: `display_only`.

This is consistent with the square being near the marked P0. It is not proof
that the physical center is exactly `(0, 0) mm`: the observed ~2 mm X offset is
within the current display-only calibration uncertainty and target-centroid
segmentation error. No GRBL command was sent.

## Operational Boundary

The dashboard currently proves: RGB target detection, aligned depth, camera
XYZ, and a validated display-only P0-plane estimate. It does not authorize
automatic writer motion. Any later motion test must use a separate bounded GRBL
command, an explicit human confirmation, and physical observation of the pen.
