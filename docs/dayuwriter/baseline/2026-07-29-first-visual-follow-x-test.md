# First Visual Follow X-Axis Test

## Preconditions Confirmed By The Operator

- The red square center was physically placed at `X+5 mm, Y=0` from P0.
- The pen tip was suspended and physically aligned to P0.
- The CNC V3 12 V supply was connected.
- At least 10 mm of unobstructed X+ travel was available.

## Visual Proposal

The fixed P0 visual baseline was `X=1.927 mm, Y=0.169 mm`.

The display-only camera proposal was:

```text
visual target: X=6.079 mm, Y=-1.621 mm
proposed delta: X=4.152 mm, Y=-1.790 mm
```

The unexpected Y component was not sent. The operator explicitly confirmed an X-only test.

## GRBL Evidence

```text
TX intent: X+4.152 mm at 50 mm/min
pre:   <Idle|MPos:0.000,0.000,0.000|FS:0,50|Pn:P|WCO:21.463,-47.388,0.000>
RX:    ok
final: <Idle|MPos:4.150,0.000,0.000|FS:0,0|Pn:P>
```

## Physical Observation

The operator confirmed that the pen moved right by approximately 4.15 mm.

## Scope Of This Evidence

This validates the bounded path from a visual XY proposal through Python and GRBL to a physical X-axis movement. It does not establish that the pen reached the red-square center. The current camera-plane mapping has approximately 1-2 mm residual error, and the unexpected Y proposal must be corrected with additional known XY observations before full two-axis target following is claimed.
