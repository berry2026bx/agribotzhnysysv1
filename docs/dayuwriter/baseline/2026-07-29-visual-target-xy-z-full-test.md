# Visual Target XY And Z Full Test

## Preconditions Confirmed By The Operator

- The pen tip was physically returned to the manual P0 mark.
- The CNC V3 12 V supply was connected and the pen tip was suspended.
- The full proposed XY path was clear and at least 1 mm of downward Z
  clearance was available.

## Target Selection Correction

The initial live stream alternated between the intended red square near RGB
pixel `(686,504)` and a false red component near `(248,44)`. The latter
projected far outside the A4 plane and was safely rejected before any motion.

The display-only dashboard was updated to accept a red candidate only when
its pixel centre projects inside the registered A4 reference board. After the
dashboard restarted and the reference was `ready`, it consistently selected
the intended paper target near `(686.4,503.6)`.

## Live Visual Proposal

The saved P0 visual baseline is `X=1.927 mm, Y=0.169 mm`. The fresh execution
snapshot reported:

```text
visual target: X=14.008 mm, Y=-15.002 mm
proposed delta: X=12.081 mm, Y=-15.171 mm
```

The coordinate sign is the registered writer-paper convention. It is the
coordinate used for the command, independent of an informal placement label.

## GRBL Execution Evidence

One persistent `COM4` session executed the following relative sequence at
50 mm/min:

```text
X+4.027, X+4.027, X+4.027
Y-3.793, Y-3.793, Y-3.793, Y-3.793
Z+1.000
```

Every segment returned `ok` and reached `Idle`. The final controller report
was:

```text
<Idle|MPos:12.075,-15.175,1.000|FS:0,0|Pn:P>
```

## Physical Observation

The operator confirmed that the pen tip arrived near the red-square centre and
then moved downward by approximately 1 mm.

## Scope And Limits

This validates one supervised end-to-end demonstration: paper-contained red
target detection, display of its planar coordinate, bounded XY motion, and a
final 1 mm Z+ drop. It does not establish an exact XY error in millimetres,
continuous unattended target tracking, object grasping, automatic homing, or
safe operation after the camera, reference board, paper, or P0 changes.
`MPos` is open-loop GRBL state; the operator observation above is the
physical-motion evidence.
