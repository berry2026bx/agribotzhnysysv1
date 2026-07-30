# Bounded Visual Target Move With Optional Z Drop

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

The default 1 mm deadband suppresses visual jitter. The initial supervised
demonstration accepts a target within plus or minus 60 mm of P0 on either axis.
Each remaining X or Y displacement is automatically split into segments no
greater than 5 mm at 50 mm/min. This is rough supervised positioning: the
current A4 plane mapping has about 1--2 mm residual error.

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

## Move To Target, Then Lower Z Slightly

This is a positioning demonstration, not a grab: no gripper is installed.
It uses the existing physical convention where `Z+` moves downward. It first
executes every X and Y segment, waiting for final `Idle` after each segment,
and only then issues one `Z+1 mm` jog at 50 mm/min. A controller error stops
the sequence before later segments and before Z.

Before the command, the operator must physically return the pen to P0, place a
flat red square within 60 mm of P0 in either direction, keep the pen suspended,
confirm the full XY path is clear, and confirm at least 1 mm of clear downward
space. The D435i, A4 reference board, and paper must not have moved since the
dashboard reached `ready`.

First run the preview command above. It must show the expected rough target
coordinate and `proposed GRBL` lines, including a final `Z1 F50` line. Then
run the following explicit execution command:

```powershell
& "C:\Users\Administrator\.conda\envs\dayuwriter-control\python.exe" `
  -m communication.dayuwriter.visual_follow `
  --port COM4 `
  --baseline-x 1.927 `
  --baseline-y 0.169 `
  --z-drop-mm 1 `
  --execute `
  --physical-preflight `
  --z-drop-preflight
```

No serial port is opened without `--execute`. A positive `--z-drop-mm` is
rejected unless `--z-drop-preflight` is present. The command remains bounded:
per-axis target delta at most 60 mm, every X/Y segment at most 5 mm, and Z
drop at most 1 mm. Do not run it unattended or assume that `MPos` is a
physical encoder measurement.

## Finite XY Follow Session

This mode starts only after the pen has been physically aligned to P0. With
the default return mode, every successful target cycle is P0-to-target, a
10-second hold, and target-to-P0; it does not lower Z. The next cycle is armed
only after the red square has visibly changed, so an unmoved target is not
replayed repeatedly.

The session accepts only a `ready` dashboard with all reference checks intact.
It requires three target samples whose X and Y spread is at most 1 mm. It
stops on a camera/reference/target failure or when a target is more than
60 mm from the captured P0 visual baseline on either axis. Each session is
bounded to at most 10 target-return cycles and 120 observations (about 30 s).

Before each real session, physically confirm that the pen is at P0, 12 V is
connected, the pen tip is suspended, the entire XY path is clear, and the
camera, A4 board, and paper have not moved. A manual push, power/USB loss,
GRBL reset, serial error, or suspected lost step invalidates the assumed pose;
stop and physically return to P0 before another session.

The default `--return-to-p0` mode sends its XY-only return after every
successful target, not only when the session ends. It does not return after a
target/reference/serial/controller error. The outbound and return routes must
both be clear before starting. The command below uses 500 mm/min, the current
bounded XY commissioning limit. The live GRBL configuration reports
`$110=$111=2000 mm/min`, but that configuration value alone does not prove the
mechanics can run stably at that speed; use a lower `--feed` value if the
machine misses steps or vibrates.

```powershell
& "C:\Users\Administrator\.conda\envs\dayuwriter-control\python.exe" `
  -m communication.dayuwriter.visual_follow `
  --port COM4 `
  --baseline-x 1.927 `
  --baseline-y 0.169 `
  --continuous `
  --return-to-p0 `
  --hold-at-target-seconds 10 `
  --max-moves 1 `
  --max-observations 120 `
  --feed 500 `
  --execute `
  --physical-preflight
```

The process must not be used for arbitrary targets outside the initial
plus-or-minus 60 mm P0 envelope. Cut 12 V for a physical emergency stop.

## Armed Repeat Follow

To leave the pen at P0 and wait for the next red-square placement, add
`--wait-for-target-change`. Startup records the existing target but sends no
motion. A new target must differ from that recorded target by at least 1 mm on
X or Y and remain stable for three samples before the first cycle begins.

The following current-setup command permits up to 10 supervised cycles. It
uses this currently registered A4-board P0 mapping. Do not use it after the
camera, board, paper, or physical P0 alignment has moved; validate the mapping
and establish the current baseline again first.

```powershell
& "C:\Users\Administrator\.conda\envs\dayuwriter-control\python.exe" `
  -m communication.dayuwriter.visual_follow `
  --port COM4 `
  --baseline-x 0 `
  --baseline-y 0 `
  --continuous `
  --wait-for-target-change `
  --max-moves 10 `
  --execute `
  --physical-preflight
```
