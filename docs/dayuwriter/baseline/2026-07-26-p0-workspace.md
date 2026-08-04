# P0 Workspace Baseline

Date: 2026-07-26

The current physical position is marked as the manual session reference `P0 = (X0, Y0)`. It is not a homed machine origin and must be physically realigned after power loss, manual movement, or controller reset.

## Observed Directions

- `X+`: right
- `X-`: left
- `Y+`: forward
- `Y-`: backward
- `Z+`: down
- `Z-`: up

## Measured Clearance From P0

| Direction | Measured clearance |
|---|---:|
| X- / left | 200 mm |
| X+ / right | 200 mm |
| Y+ / forward | 150 mm |
| Y- / backward | 100 mm |

## Software Safety Envelope

After reserving 10 mm before each measured mechanical boundary:

- X: `-190 mm <= X <= +190 mm`
- Y: `-90 mm <= Y <= +140 mm`
- Z: not yet bounded; relative low-speed jogs only

The GRBL travel settings are not changed because homing and a repeatable machine origin have not been established.
