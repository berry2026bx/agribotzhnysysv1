# Live Coordinate Readout

## Goal

Make the dashboard's existing machine-plane red-target coordinate visible at a
glance instead of requiring the operator to inspect raw JSON.

## Decision

The display-only dashboard will show a fixed `Target relative to P0` section
with X and Y values in millimetres and a short state line. It renders finite
`machine_xy_mm` values only when the dashboard state and mapping are both
`ready`/`available`; otherwise both numeric fields are cleared to `--`.

## Boundary

This is a display-only UI change. It creates no motion controls, no serial
access, and no new calibration or coordinate source.
