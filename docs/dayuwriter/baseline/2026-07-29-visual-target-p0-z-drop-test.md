# Visual Target P0 Z-Drop Test

## Preconditions Confirmed By The Operator

- The pen tip was physically re-aligned to the manual P0 mark.
- The red square's geometric center was physically aligned to P0.
- The CNC V3 12 V supply was connected and the pen tip was suspended.
- The full XY path was clear and at least 1 mm of downward Z clearance was
  available.

## Live Visual Snapshot

The display-only dashboard reported a ready mapping. With the saved visual P0
baseline `X=1.927 mm, Y=0.169 mm`, the explicit preview reported:

```text
visual target: X=1.228 mm, Y=-0.616 mm
proposed delta: X=-0.699 mm, Y=-0.785 mm
proposed GRBL: $J=G91 G21 Z1 F50
preview only; no serial port opened
```

Both XY deltas were within the 1 mm visual deadband, so the bounded runner
correctly proposed no XY command. This is consistent with a red square near
P0; it is not evidence of sub-millimetre camera accuracy.

## GRBL Execution Evidence

The explicit execution read a fresh ready frame and sent only the final Z
command:

```text
visual target: X=1.203 mm, Y=-0.652 mm
proposed delta: X=-0.724 mm, Y=-0.821 mm
proposed GRBL: $J=G91 G21 Z1 F50
accepted: ok
final: <Idle|MPos:0.000,0.000,1.000|FS:0,0|Pn:P>
```

## Physical Observation

The operator confirmed that the pen carriage moved downward by approximately
1 mm.

## Scope Of This Evidence

This validates the first supervised visual-target command at P0 with an
optional, bounded `Z+1 mm` action. It does not validate XY target following
away from P0, target-centre precision, Z contact/probing, or grabbing. `MPos`
is open-loop GRBL state and the physical observation above, not `MPos` alone,
is the evidence of the Z motion.
