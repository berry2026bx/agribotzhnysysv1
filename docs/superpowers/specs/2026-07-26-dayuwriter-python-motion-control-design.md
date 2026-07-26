# DayuWriter Python Motion Control Design

Date: 2026-07-26
Status: Approved scope, pending written-spec review

## Objective

Provide a small Python API and command-line tool for safely controlling the verified DayuWriter GRBL device on Windows. The first version supports a persistent serial connection, status queries, and bounded relative jogs only.

## Current Hardware Baseline

- Windows port: `COM3`
- Serial settings: 115200 baud, 8-N-1, no flow control
- Firmware: `Grbl 1.1f kvenjoy.com.20170131`
- X, Y, and Z movement have been physically observed.
- Current `$3=4` is preserved; positive Z moves the pen carriage downward.
- Homing is disabled (`$22=0`), and no repeatable machine origin has been verified.
- The manually marked `P0` is a physical reference point, not an automatic GRBL machine origin.

## Scope

The controller will:

- open one persistent pySerial connection;
- wait for the Arduino/GRBL startup interval;
- query and parse real-time `?` status reports;
- reject jogs unless GRBL reports `Idle`;
- send only bounded `$J=G91` relative jog commands;
- wait for `ok`, `error:`, or `ALARM:` responses with a deadline;
- poll until the controller returns to `Idle` after an accepted jog;
- close the serial port reliably;
- expose a CLI requiring an explicit port, axis, distance, and feed.

The controller will not:

- send `G92`, `$H`, `G0`, `G1`, or arbitrary G-code;
- modify GRBL `$` settings or flash firmware;
- infer the physical position from `MPos` after a reset;
- automatically move when imported, opened, or connected;
- implement absolute coordinates, homing, camera calibration, or vision motion.

## Components

### Protocol Layer

The existing `grbl_protocol.py` remains the source for response classification. It will gain a narrowly validated relative-jog encoder. Axis must be `X`, `Y`, or `Z`; distance must be finite and non-zero; feed must be finite and positive.

### Persistent Controller

`GrblController` owns one serial connection for its full lifetime. Opening the port and moving are separate operations. The controller reads startup output, obtains a current status, and sends no motion until the caller explicitly requests a jog.

The controller treats `ok` as command acceptance only. Completion is established by polling `?` until `Idle`, not by assuming the mechanism moved. Physical observation and later calibration remain separate evidence.

### Command-Line Interface

The CLI requires all motion arguments explicitly. Initial limits are conservative:

- maximum absolute distance per invocation: 5 mm;
- maximum XY feed: 100 mm/min;
- maximum Z feed: 50 mm/min.

The CLI prints pre-motion status, the accepted command, controller responses, and final status. It exits non-zero on timeout, serial failure, `error:`, `ALARM:`, or a non-Idle precondition.

## Data Flow

1. User invokes the CLI with explicit arguments.
2. The controller opens `COM3` and waits for possible board reset.
3. It sends `?` and requires an `Idle` response.
4. The protocol layer validates and encodes one relative jog.
5. The controller sends the jog and requires `ok` before the deadline.
6. It polls `?` until `Idle` or timeout.
7. It reports the raw responses and closes the port.

## Error Handling

- Port missing or busy: report the pySerial error and do not retry automatically.
- Startup/status timeout: fail without sending a jog.
- Non-Idle state: fail without sending a jog.
- Invalid axis, distance, or feed: reject locally before opening the port.
- GRBL `error:` or `ALARM:`: stop and report the raw line.
- Completion timeout: report uncertainty; do not send another movement automatically.

## Testing

Offline tests will use fake serial and clock objects. They will verify:

- no movement is sent before an `Idle` status;
- validation rejects arbitrary commands and out-of-bounds jogs;
- correct `$J=G91` bytes are emitted;
- `ok` is distinguished from final `Idle`;
- error, alarm, and timeout paths fail closed;
- the port is closed after success and failure;
- importing the module produces no serial or motion side effects.

The first live test will use `X+1 mm` at 50 mm/min from the marked safe area. Y and Z live tests require separate physical confirmation.

## Acceptance Criteria

- All offline tests pass in `dayuwriter-control`.
- A dry status query produces no motion.
- A single explicit X jog is accepted and physically observed.
- The program performs no automatic origin setting, parameter write, homing, or follow-up movement.
