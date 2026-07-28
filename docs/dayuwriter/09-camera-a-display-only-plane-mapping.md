# Camera A Display-Only Plane Mapping

## Current Result

Camera A serial `231122070403` was held in a fixed oblique pose.  Four
pen-tip observations at known DayuWriter XY positions fit a pixel-to-machine
plane mapping.  The center point `(30, 30)` mm was held out from fitting and
used only for validation.

The result JSON records the measured held-out error.  It is not a permission
to command the DayuWriter, because the point pixels were manually selected
and the machine is open loop.

## Run in VS Code Terminal

```powershell
conda activate dayuwriter-control
python -m vision.realsense.plane_mapping `
  --input docs/dayuwriter/calibration/camera-a-current-pose-input.json `
  --output docs/dayuwriter/calibration/camera-a-current-pose-result.json `
  --predict-u 338 --predict-v 345
```

The second output line is a JSON prediction.  It contains
`motion_permission: display_only` and does not open `COM4`.

## Invalidation Rules

Create a new artifact if the camera, machine frame, paper plane, pen Z height,
camera serial, or P0 reference changes.  Camera B must use its own references
and its own output artifact.
