# DayuWriter Device Baseline

## Record Metadata

- Date and time: 2026-07-26 (China Standard Time; exact command timestamps retained in terminal history)
- Operator: berry2026bx
- Computer and OS: Windows 11 Professional Education, 64-bit, build 26200
- Machine label/version marking: not observed
- Evidence files or photographs: pending physical inspection

## Safety State

- USB disconnected at start: yes
- 12 V disconnected at start: yes
- Tool clear of surface: user confirmed before USB connection
- 12 V disconnect reachable: not yet physically inspected
- Notes: USB was connected only after explicit confirmation that 12 V remained disconnected.

## Unpowered Hardware

- Controller markings: not observed
- Shield markings: not observed
- Driver count/orientation: not observed
- XY motor connectors: not observed
- Z motor connector: not observed
- Limit switches physically present: not observed
- Adapter label and polarity: not observed
- Belts, pulleys, rails, lead screw, coupler, wiring: not observed

## Windows USB Identity

- Device Manager before: `通信端口 (COM1)` only; no CH340 device
- Device Manager after: `通信端口 (COM1)` and `USB-SERIAL CH340 (COM3)`
- Device name: `USB-SERIAL CH340 (COM3)`
- COM port: `COM3`
- Hardware IDs: `USB\\VID_1A86&PID_7523&REV_0264`, `USB\\VID_1A86&PID_7523`
- VID/PID: `1A86:7523`
- PnP instance ID: `USB\\VID_1A86&PID_7523\\5&2CF64626&0&1`
- Driver provider/date/version: `wch.cn`, `2024-09-16`, `3.9.2024.9`
- INF: `oem124.inf`
- Signature: `Microsoft Windows Hardware Compatibility Publisher`; `IsSigned=True`
- Warning icon/status: no warning; `Status=OK`, `CM_PROB_NONE`
- pySerial enumeration: `COM3`, description `USB-SERIAL CH340 (COM3)`, hardware ID `USB VID:PID=1A86:7523`, location `1-1`

## Read-Only GRBL Evidence

- 12 V disconnected during capture: not yet captured
- Baud and framing: not yet opened; planned `115200`, 8-N-1
- Boot banner: not yet captured
- `$I`: not yet captured
- `$$`: not yet captured
- `$#`: not yet captured
- `$G`: not yet captured
- `?`: not yet captured
- Raw capture path: pending

## Powered Static Inspection

- USB connected before 12 V: not yet attempted
- 60-second observation result: not yet attempted
- Motor/driver temperature observation: not yet attempted
- Noise/vibration/smell: not yet attempted
- Status after 12 V: not yet attempted

## First Jog

- Preconditions passed: not yet reviewed
- Exact command: not attempted
- Start/end state: not attempted
- Reported coordinate change: not attempted
- Observed direction/distance: not attempted
- Noise/vibration/stall/step loss: not attempted
- Result: not attempted

## Historical Leads, Not Current Facts

- Historical port: `COM11`
- Historical firmware banner: `Grbl 1.1f kvenjoy.com ['$' for help]`
- Historical parameter claims: `$100/$101=80`, `$110/$111=2000`, among contradictory snapshots
- Historical motion observations: prior XY/Z movement with collisions, vibration, and direction/limit uncertainty

## Unknowns and Next Decision

- Unresolved unknowns: physical board/version, current GRBL firmware, all settings, mechanical condition, limits, travel, directions, and 12 V wiring
- Stop condition encountered: none during USB enumeration
- Approved next action: capture the read-only GRBL baseline on COM3 with 12 V still disconnected

