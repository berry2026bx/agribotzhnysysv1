# A4 ArUco Reference Board

## Purpose

This board makes the camera-to-writer XY display recoverable after D435i A is
re-mounted. It does not move the writer. The local web page remains
`display_only` and has no GRBL controls.

The reference board must stay fixed relative to the writer P0 frame. You may
transport the writer with the secured board, or change camera A's position and
angle. You must repeat physical board registration only when the board itself,
its height or tilt, or P0 relative to the writer changes.

## Print And Mount

1. Open [a4-aruco-v1.svg](../reference-board/a4-aruco-v1.svg) and print it at
   `100%` / actual size. Do not select fit-to-page or scaling.
2. Measure the printed 100 mm verification scale. Do not use the board unless
   it measures 100 mm.
3. Attach the sheet to a flat, rigid backing. Fix the backing on the same plane
   as the red target or paper. It must not sit below the machine, bend, or move
   independently of the writer.
4. Keep all six numbered markers visible to camera A during operation.

## Register Board To P0

This is a one-time physical operation after mounting a new board.

1. Keep the pen tip clear of the paper and write surface.
2. Rotate the board so its printed X+ direction points toward the writer's
   physical X+ direction (right in the previously verified setup) and its
   printed Y+ direction points toward physical Y+ (forward).
3. Put the pen tip on the printed P0 cross. This must be the existing physical
   P0 mark used by the writer, not a new origin.
4. From P0, use a bounded X+30 mm jog. The pen tip must land on the printed
   `X+30 mm` cross to the right of P0. Return to P0, then use a bounded Y+30
   mm jog; the pen tip must land on the printed `Y+30 mm` cross below P0.
5. Adjust the board physically until all three checks are correct, then secure
   the rigid backing.
6. Use the Register board button on the local page and
   tick the confirmation only after the three physical alignments are complete.

The button records the confirmation. It does not command a motor, send G-code,
or redefine a GRBL machine coordinate.

## Start Camera A

Close RealSense Viewer and any older dashboard instance that owns camera A.
Activate the established environment, then run:

```powershell
conda activate dayuwriter-control
python -m vision.realsense.live_red_target_dashboard --serial 231122070403 --aruco-reference-board --reference-registration docs/dayuwriter/calibration/camera-a-a4-aruco-registration.json --port 8765
```

Open <http://127.0.0.1:8765/>. The dashboard discards 90 startup frames and
then collects 12 complete frames containing all six markers.

## Interpret Status

- `registration_required`: physically align and confirm the board first.
- `collecting_reference_frames`: keep camera and board steady while the 12
  complete frames are collected.
- `ready`: the held-out markers passed the display-only quality gate: mean
  error at most 1.5 mm and maximum error at most 3.0 mm. The page may display
  red-target machine XY.
- `reference_lost`: one or more required markers are missing or invalid. The
  page intentionally omits valid machine XY.
- `calibration_rejected`: the independent marker error exceeded the quality
  gate. Reposition camera A, improve illumination, or inspect the board.

The page still shows RGB, depth, and camera XYZ when possible. Camera XYZ is
not writer XYZ. Moving the red target does not require recalibration.

## Transport And Re-mount

Transport the writer with the rigid board attached. At the next location,
mount camera A so it can see every marker, start the same command, and wait for
`ready`. Camera re-mounting alone does not require P0 registration.

If the board slips, is replaced, changes height or tilt, or P0 is redefined,
repeat **Register Board To P0** before trusting display XY. Targets above the
board plane require the later 3D camera-to-machine stage; this board only
validates planar XY display.
