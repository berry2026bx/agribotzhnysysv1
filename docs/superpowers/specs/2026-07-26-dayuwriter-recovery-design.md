# DayuWriter Win11 Recovery and First Motion Design

## Goal

Restore the current DayuWriter on a replacement Windows 11 computer using live evidence. The first milestone ends after USB identity, read-only GRBL capture, powered static inspection, and one short low-speed jog.

Python automation, coordinate calibration, D435i perception, camera-to-machine calibration, and detector-driven motion are separate later milestones.

## Evidence Rules

- Treat historical `COM11`, `Grbl 1.1f kvenjoy.com`, steps/mm, rates, travel, Z direction, and machine version as leads only.
- Do not flash firmware, write `$x=value`, reset EEPROM, send `G92`, home, or move before the live read-only baseline is reviewed.
- `ok` acknowledges parsing/queueing; it does not prove that physical motion finished.
- `MPos` and `WPos` are open-loop controller estimates, not encoder measurements.
- `Ctrl-X` is GRBL soft reset, not a certified hardware emergency stop. The first powered test requires direct access to the 12 V power disconnect.

## Gates

### Gate 0: Unpowered inspection

Keep both USB and 12 V disconnected. Record the controller, shield, driver orientation, motor connectors, limit-switch connectors, power label, belt condition, couplers, and cable clearance.

### Gate 1: USB identity

Keep 12 V disconnected. Compare Device Manager before and after connecting USB. Record the new device name, COM number, hardware IDs, VID/PID, driver provider/version, and warning status. Do not assume `COM11`.

Allow Windows Update to install a working driver. If it fails, use the current official WCH CH341SER package. Do not run the unsigned driver bundled with cracked controller software.

### Gate 2: Read-only GRBL baseline

Open the verified COM port at 115200 8-N-1 with bounded timeouts. Capture the boot banner and complete responses to `$I`, `$$`, `$#`, `$G`, and `?`. Stop on no response, invalid text, `ALARM`, `Door`, `Hold`, or `Sleep` until the state is understood.

### Gate 3: Mechanical and electrical review

Disconnect power. Check belts, guide motion, pulley set screws, lead screw/coupler, wiring clearance, actual limit switches, adapter rating, and polarity. Rehearse how to remove 12 V immediately.

### Gate 4: Powered static observation

Reconnect USB, then connect 12 V without sending motion. Stop immediately for spontaneous motion, sustained vibration, abnormal heat, smell, smoke, arcing, or an unexpected GRBL state.

### Gate 5: First jog

Use one GRBL `$J=` jog at a time, approximately 1 mm at low feed. Do not use absolute motion, `G92`, homing, or a G-code file. Poll status with a deadline and visually verify the real direction and distance. Test Z separately at a smaller distance and lower rate after XY is understood.

## Existing Software Decision

- `aceshi.py`, `bzhongjian.py`, `c.py`, `d.py`, `calibrate_camera.py`, and `full_loop.py` are prohibited as recovery tools because they move automatically, modify state, assume geometry, or lack bounded failure handling.
- `verify_basic.py` is not used unchanged because it requires 12 V, hard-codes `COM11`, and treats historical settings as expected values.
- The local UGS tree identifies itself as 2.1.22, but its Windows launcher is unsigned and has not been matched to an official release digest. It may be used later for a read-only console and manual jog only after provenance review.
- The signed legacy WCH driver files are fallback material; Windows automatic installation and the current official WCH package take precedence.

## Completion Criteria

- Windows consistently identifies the current USB serial device without warnings.
- The raw GRBL identity and read-only configuration are saved.
- No historical port, parameter, direction, or travel value is silently inherited.
- Static 12 V operation is normal.
- One short XY jog completes without collision, vibration, step loss, or abnormal sound.
- No firmware flash, EEPROM write, `G92`, or homing occurred.

## Later Milestones

1. A bounded Python GRBL transport and controller.
2. Measured machine directions, scale, repeatability, backlash, and usable workspace.
3. D435i camera-only validation and fixed mounting.
4. Camera-to-machine calibration with independent held-out validation points.
5. Detection-only coordinate output, then human-confirmed lifted-tool motion.

