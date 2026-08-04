# Camera Coordinate Label Design

## Goal

Replace the camera-frame coordinate label's opaque black treatment with a
lighter annotation that remains readable over the A4 work surface.

## Approved Design

- Use a semi-transparent white label background.
- Use a thin red border matching the detected-target box.
- Use dark gray coordinate text with a subtle shadow.
- Keep the label offset to the right of the target box.
- Hide the label whenever no valid detected target coordinate is available.

## Boundary

This is a display-only CSS change to the local D435i dashboard. It does not
change target detection, coordinate calculation, dashboard polling, serial
access, GRBL motion, or calibration data.
