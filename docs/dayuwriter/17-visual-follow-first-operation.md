# First Bounded Visual Follow Operation

The D435i dashboard and GRBL control remain separate. The dashboard at `http://127.0.0.1:8765/` has no serial access. The command below reads its `state.json` and is preview-only unless both execution flags are present.

## Current Live Session

- Camera: D435i A, serial `231122070403`.
- Live dashboard: `http://127.0.0.1:8765/`.
- Current CH340 device identity: `USB-SERIAL CH340 (COM4)`.
- Captured P0 visual baseline: `X=1.927 mm`, `Y=0.169 mm`.

The baseline is valid only while the A4 board and camera stay fixed and the red square was centered on physical P0 when the baseline was captured. It represents a visual offset, not an encoder or a machine home.

## Preview

With the red square at another physical location, run this from the repository root:

```powershell
& "C:\Users\Administrator\.conda\envs\dayuwriter-control\python.exe" `
  -m communication.dayuwriter.visual_follow `
  --baseline-x 1.927 `
  --baseline-y 0.169
```

The command prints the target, baseline, delta, and exact bounded GRBL jog strings. It must end with `preview only; no serial port opened`.

The default 1 mm deadband suppresses visual jitter. Each remaining X or Y segment is constrained to 5 mm or less and 50 mm/min. A larger target delta is rejected; it is not split or executed.

## First Physical Test

For the first test, put the red square at physical `X+5 mm, Y=0` while the pen is physically aligned to P0. The preview should show a delta near `X=+5 mm, Y=0 mm`.

Only after confirming all of the following at action time may the explicit execution form be used:

- 12 V is connected to the CNC V3 board.
- The pen tip is suspended and the pen is physically at P0.
- At least 10 mm of unobstructed X+ path remains.
- The camera, reference board, and paper have not moved.
- The preview shows the expected small positive X delta.

```powershell
& "C:\Users\Administrator\.conda\envs\dayuwriter-control\python.exe" `
  -m communication.dayuwriter.visual_follow `
  --port COM4 `
  --baseline-x 1.927 `
  --baseline-y 0.169 `
  --execute `
  --physical-preflight
```

Successful execution requires command acceptance (`ok`), final `Idle`, and direct observation of the pen motion. `ok` alone is not motion proof. Cut 12 V for a physical emergency stop.
