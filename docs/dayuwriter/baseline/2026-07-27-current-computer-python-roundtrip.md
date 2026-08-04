# Current Computer Python Persistent-Session Round Trip

Date: 2026-07-27

## Preconditions Confirmed On Site

- The pen carriage was physically aligned to P0.
- The pen tip was suspended above the work surface.
- The X positive direction had at least 1 mm of free travel.
- The 12 V CNC supply was connected.
- The live CH340 port was `COM4`.

## Command Sequence

One `GrblController` instance kept `COM4` open for the entire sequence:

```text
status
jog X +1.0 mm at 100 mm/min
jog X -1.0 mm at 100 mm/min
status
```

## Observed Result

```text
pre:      <Idle|MPos:0.000,0.000,0.000|...>
forward:  accepted=ok; final=<Idle|MPos:1.000,0.000,0.000|...>
backward: accepted=ok; final=<Idle|MPos:0.000,0.000,0.000|...>
final:    <Idle|MPos:0.000,0.000,0.000|...>
```

The user confirmed that the carriage physically returned to the P0 mark.

## Actual GRBL Motion Payloads

```text
$J=G91 G21 X1 F100
ok
$J=G91 G21 X-1 F100
ok
```

During both moves, GRBL reported intermediate `Jog` states and then the final `Idle` state. This is a real serial protocol record, not a simulated log.

## Important Constraint

Opening a new serial session resets the controller's software coordinate to zero even though the machine has no encoder or homing reference. Therefore, after any serial reconnect:

1. physically align the carriage to P0 before treating `MPos=0` as P0;
2. keep one `GrblController` session open for any sequence that depends on coordinates;
3. require a final `Idle` state and physical observation before accepting a motion result.

This validates one small X-axis round trip only. It does not validate large-range repeatability, backlash, camera-to-P0 calibration, or automatic motion.
