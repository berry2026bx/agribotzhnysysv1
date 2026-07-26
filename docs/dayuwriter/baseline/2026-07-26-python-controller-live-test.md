# Python Controller Live Test

Date: 2026-07-26
Port: `COM3`

The bounded Python CLI completed two consecutive relative X jogs:

```text
python -m communication.dayuwriter.grbl_jog --port COM3 --axis X --distance 5 --feed 100
```

Each invocation reported a pre-motion `Idle` status, `accepted: ok`, and a final `Idle` status at `MPos X=5.000`. The user independently confirmed correct physical motion for a cumulative X displacement of approximately 10 mm.

Because opening the serial port resets this GRBL board, each CLI invocation reports coordinates from a new session. The physical displacement is cumulative even though each invocation reports `0 -> 5 mm`.
