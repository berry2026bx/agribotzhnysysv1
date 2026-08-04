# Bounded Visual Target Move With Z Drop

## Goal

Turn the existing display-only red-square coordinate into one explicitly
confirmed DayuWriter motion: move from physical P0 to that target in bounded
XY segments, then optionally issue one small downward Z jog.

## Fixed Decisions

- The dashboard remains display-only and never opens a serial port.
- The operator places the pen at physical P0 before every execution. The
  red-square coordinate is interpreted relative to the captured visual P0
  baseline (`X=1.927`, `Y=0.169` mm) while the A4 board and camera remain
  unchanged.
- Initial execution is limited to a target displacement of 30 mm per XY axis.
  Every GRBL jog is at most 5 mm, with XY feed at most 100 mm/min.
- Z is opt-in. `Z+` is the already measured downward direction and the new
  command permits at most `+1 mm` at 50 mm/min.
- `--execute` requires `--physical-preflight`; Z additionally requires
  `--z-drop-preflight`. No flag means preview only and no serial port opens.

## Execution Order And Failure Behavior

The runner reads one `ready`, `display_only` dashboard snapshot, computes the
target-minus-baseline delta, checks the 30 mm demo envelope, then opens one
persistent `GrblController`. It executes all X segments first, then Y
segments. The controller already waits for `ok` and final `Idle` for every
segment. Only after every XY result is returned does it issue the optional Z
command. A controller failure propagates, so later XY segments and Z are not
sent.

## Evidence Boundary

The current A4 mapping has roughly 1--2 mm residual error. This feature is a
rough, supervised positioning demonstration, not a precision placement or
grasping system. It cannot grab because no gripper exists. A returned `ok` is
command acceptance; final `Idle` and direct observation remain required.

## Approval Context

This design implements the user's already approved request on 2026-07-29:
rough red-square coordinate display, bounded XY motion, then a slight Z drop.
