# D435i Camera A Runtime Error Summary

Date: 2026-07-27

## Final Status

Camera A can now be opened from the project Conda environment and can provide:

- RGB frames;
- aligned depth frames;
- a metric depth value in metres;
- a deprojected camera-coordinate point.

The verified device is D435i serial `231122070403`. The successful baseline is:

`baseline/camera-a-current-computer.json`

The current computer used `pyrealsense2 2.58.3` from the `dayuwriter-control` environment. The Viewer was not running during the successful capture.

## Observed Errors and Causes

### 1. `depth must be finite and greater than zero: 0.0`

The camera stream was running, but the requested colour-centre pixel `(320, 240)` had no valid aligned depth. The full frame still contained valid depth pixels, so this was a local depth hole caused by the observed scene and alignment, not proof of a failed camera.

Evidence:

- the corrected diagnostic received frames successfully;
- valid depth ratio was approximately 14.6% to 18.0% in the observed scene;
- the nearest valid point could be about 36 pixels from the requested centre.

修复：`camera_probe` now searches outward from the requested centre for a finite positive sample. The selected pixel is recorded in `center_sample.pixel_uv`, and the requested centre, strategy, and radius are recorded in `depth_sampling`.

For this scene, the verified command used `--depth-sample-radius 50`. A smaller radius can still fail if the local depth hole is larger than that radius.

### 2. `Permission denied` while writing the JSON file

This occurred on the other computer when writing the existing project path:

`docs\\dayuwriter\\baseline\\camera-a-final-computer.json`

The exact Windows cause was not proven. The file or directory may have been read-only or locked by another process. It was an output-path permission problem, not a RealSense measurement result.

On the current computer, writing the new file `camera-a-current-computer.json` succeeded. Using a new user-writable path avoids overwriting the problematic file until its attributes or lock state are inspected.

### 3. `Frame didn't arrive within 5000/10000`

The first diagnostic command contained this pattern:

```python
[p.wait_for_frames() for _ in range(30)]
```

That list retains every returned `frameset`. RealSense uses a finite frame pool; retaining approximately 16 frames can block delivery of the next frame. The observed failure at exactly frame 16 matched this mistake. The upstream librealsense issue is documented at:

https://github.com/realsenseai/librealsense/issues/946

This was an error in the temporary diagnostic command, not evidence that the camera could only produce 16 frames.

The corrected warm-up discards each frame immediately, for example:

```python
for _ in range(30):
    pipeline.wait_for_frames()
```

With the corrected form, the current computer received the warm-up frames and produced the successful baseline.

### 4. `pnputil /restart-device ... Access is denied`

The attempt to restart the exact D435i USB composite device was rejected because the terminal was not elevated. This was a Windows privilege limitation. Physical USB unplug/replug was used instead; it did not require firmware changes.

### 5. Base Python could not import `pyrealsense2`

The default `C:\\ProgramData\\anaconda3\\python.exe` did not contain the RealSense Python wrapper. The project environment did contain it. Running the project with the base interpreter would therefore give a misleading import failure.

Use:

```cmd
conda activate dayuwriter-control
```

or explicitly use the project environment through `conda run -n dayuwriter-control`.

### 6. Viewer 3D view was sparse

The RGB view was clear while the 3D/depth view contained holes. This is consistent with invalid depth pixels from low-texture, dark, reflective, or occluded surfaces. The 3D display was not used as the acceptance criterion; the Python aligned-depth baseline is the relevant test.

## Verification Result

The following passed after the sampling change:

```text
113 passed
```

The final baseline record contains:

- colour and depth streams at `640x480 @ 30 FPS`;
- depth scale approximately `0.001 m` per Z16 unit;
- an actual valid sample pixel;
- a positive metric depth;
- a finite deprojected camera point;
- camera serial `231122070403`.

## Scope Boundary

This establishes Camera A acquisition and pixel-to-camera-coordinate conversion only. It does not yet establish:

- the final rigid camera mount;
- camera-to-P0 extrinsics;
- a P0 plane calibration;
- target detection;
- automatic DayuWriter motion;
- Camera B calibration.

The next hardware step must keep the DayuWriter 12 V disconnected while a read-only GRBL baseline is captured from the currently detected CH340 port `COM4`.
