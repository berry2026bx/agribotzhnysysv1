# RealSense D435i Camera A Baseline

Date: 2026-07-27
Source: RealSense Viewer device information and Windows PnP enumeration

## Identity

- Logical label: Camera A
- Name: Intel RealSense D435I
- Serial number: `231122070403`
- ASIC serial number: `221123063869`
- Firmware update ID: `221123063869`
- Product ID: `0B3A`
- Product line: D400
- Connection type: USB
- USB type descriptor: `3.2`
- IMU: BMI085
- Advanced mode: YES
- Camera locked: YES
- Current firmware: `5.13.0.55`

## Windows Enumeration

- Intel(R) RealSense(TM) Depth Camera 435i RGB: OK
- Intel(R) RealSense(TM) Depth Camera 435i Depth: OK

## Current Decision

Do not update firmware yet. First verify RGB and depth streaming in RealSense Viewer and save a functional baseline. SDK v2.58.1 release notes list D435i firmware 5.17.3.10 or later as the supported combination, but the current lower firmware version alone does not prove that streaming is unusable. Firmware update remains a separately authorized, evidence-based step.

Camera B must use a different serial number and an independent calibration profile.
