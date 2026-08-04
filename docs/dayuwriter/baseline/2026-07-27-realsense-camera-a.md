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

## Python Read-Only Capture

Status: succeeded on 2026-07-27. RealSense Viewer was closed first so the SDK could acquire exclusive camera access.

- Command path: `python -m vision.realsense.camera_probe`
- Required serial: `231122070403`
- Source measurement record: `2026-07-27-realsense-camera-a-capture.json`
- Color stream: 640 x 480, 30 fps, `rgb8`
- Depth stream: 640 x 480, 30 fps, `z16`, scale `0.0010000000474974513` m/unit
- Depth was aligned to the color frame before sampling.
- Center sample: pixel `(320, 240)`, depth `0.16700001060962677` m, camera point `(-0.002562949899584055, -0.0017164903692901134, 0.16700001060962677)` m.
- Camera convention: +X right, +Y down, +Z forward.

The tool does not import the DayuWriter controller, open a COM port, or issue GRBL commands. The local `color.npy` and `depth.npy` capture arrays are intentionally excluded from Git because they are unreviewed raw laboratory imagery; the small JSON record preserves the reproducible numeric baseline.

## Scope Boundary

This verifies Python RGB/depth acquisition and one metric pixel-to-camera-3D conversion only. It does not establish a camera mount, a workspace plane, a camera-to-P0 transform, physical accuracy, object detection, or permission for machine motion.
