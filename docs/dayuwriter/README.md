# DayuWriter Recovery

This directory records evidence-first recovery of the DayuWriter/CoreXY motion platform.

Current phase: Windows USB identity and read-only GRBL baseline.

Safety rules:

- Keep 12 V disconnected until the USB/GRBL baseline is reviewed.
- Do not flash firmware or write GRBL settings during recovery.
- Do not run historical motion or camera-loop scripts.
- Treat `Ctrl-X` as soft reset, not a physical emergency stop.
- Record observed values; do not inherit historical `COM11`, dimensions, rates, directions, or steps/mm.

Start with [the device baseline template](templates/device-baseline-template.md) and follow [the recovery plan](../superpowers/plans/2026-07-26-dayuwriter-win11-recovery.md).

