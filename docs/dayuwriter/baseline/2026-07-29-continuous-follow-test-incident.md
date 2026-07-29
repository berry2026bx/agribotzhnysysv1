# Continuous Follow Test Incident

## What Happened

While adding a test for the new continuous-follow command-line branch, the
test unintentionally invoked the pre-existing single-target execution path on
the live `COM4` port. The test supplied `--execute`, `--physical-preflight`,
and `--z-drop-mm 1` before the new `--continuous` branch had been implemented.

GRBL accepted and completed this sequence:

```text
X+2.513 mm
X+2.513 mm
Z+1.000 mm
```

The final reported status was:

```text
<Idle|MPos:5.025,0.000,1.000|FS:0,0|Pn:P>
```

No continuous-follow behavior was exercised. The resulting physical pen
position must be treated as unknown until the operator observes it and
physically re-establishes P0.

## Correction

The test now injects a fake controller, so automated tests do not open a live
serial port. The continuous branch is checked before any existing single-move
execution logic and rejects nonzero Z drops before it can open a controller.

## Required Before Any Further Live Test

1. Inspect the pen and the machine for unintended contact or interference.
2. Physically align the pen tip to P0 again.
3. Confirm 12 V, suspended pen tip, and clear XY path at action time.
4. Put the red target within the current plus-or-minus 30 mm P0 envelope.
