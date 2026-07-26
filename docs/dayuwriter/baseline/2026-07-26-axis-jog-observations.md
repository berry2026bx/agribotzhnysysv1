# Axis Jog Observations

Date: 2026-07-26

## Conditions

- USB connected on `COM3`.
- 12 V connected to the red CNC V3 `12-36V` input.
- Pen tip held clear of paper and mechanical limits.
- Jog commands were relative `$J=G91` commands; no `G92`, homing, or parameter writes were sent.

## Results

| Axis | Command | GRBL response | Physical observation |
|---|---|---|---|
| X | `$J=G91 X1 F50` and `$J=G91 X5 F100` | `ok`, `Jog` | Moved; motor rotation heard |
| Y | `$J=G91 Y5 F100` | `ok`, `Jog` | Moved |
| Z | `$J=G91 Z1 F50` | `ok`, final `Idle` | Pen carriage moved slightly downward |

## Direction decision

The current hardware/firmware state is intentionally preserved. The baseline contains `$3=4`, which inverts the Z direction in GRBL. Under the current setup, a positive Z jog moves the carriage downward. No direction correction has been applied.
