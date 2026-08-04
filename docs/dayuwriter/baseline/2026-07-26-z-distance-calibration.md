# Z Distance Calibration

Date: 2026-07-26

- GRBL setting: `$102=100.000` steps/mm
- Commanded movement: two `Z+5 mm` jogs, 10 mm total
- Physical direction: downward
- Measured movement: approximately 10 mm
- Measurement precision: insufficient for a fine correction
- Decision: keep `$102=100.000` unchanged

After measurement, two `Z-5 mm` jogs moved the pen carriage upward by approximately 10 mm to return near its original safe height. The current coordinate convention remains unchanged: positive Z moves downward and negative Z moves upward.
