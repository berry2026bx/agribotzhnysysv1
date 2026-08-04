# XY Distance Calibration

Date: 2026-07-26

| Axis | GRBL setting | Commanded distance | Measured distance | Decision |
|---|---:|---:|---:|---|
| X | `$100=80.000` steps/mm | 20 mm | 20 mm | Keep current setting |
| Y | `$101=80.000` steps/mm | 20 mm | 20 mm | Keep current setting |

Each measurement used four consecutive 5 mm relative jogs in one persistent serial session at 100 mm/min. Each axis was then moved 20 mm in the opposite direction to return near the marked starting point. Measurement precision was limited by the user's ruler reading.
