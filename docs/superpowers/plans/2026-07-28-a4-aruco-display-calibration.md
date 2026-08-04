# A4 ArUco Display Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a printable A4 six-marker ArUco reference board and a loopback-only camera-A wizard that restores display-only pixel-to-machine XY mapping after the D435i is re-mounted.

**Architecture:** A board-layout module owns physical geometry, IDs, and machine-relative corners. A calibration module converts ArUco corners into the existing CalibrationPoint type, fits four marker IDs, and validates two held-out IDs. The local dashboard gains a board-registration action and tracker, without importing or calling any GRBL code.

**Tech Stack:** Python 3.11, NumPy, pyrealsense2, OpenCV contrib ArUco, standard-library http.server, pytest.

## Global Constraints

- Camera is D435i A serial `231122070403`. Camera B is out of scope.
- RGB/depth stream stays aligned `640 x 480` at 30 FPS. Different size rejects the session.
- Board is `a4-aruco-v1`, A4 landscape `297 x 210 mm`, dictionary `DICT_4X4_50`, six 40 mm markers with IDs 0 through 5.
- Printed P0 is `(148.5, 105.0) mm`. Board-relative machine XY is board XY minus P0 after one physical three-point registration.
- Fit marker IDs: 0, 1, 3, 4. Held-out validation IDs: 2, 5. Capture 12 complete frames after 90 warmup frames.
- Accept only held-out mean error <= 1.5 mm and maximum error <= 3.0 mm.
- Every output remains `motion_permission: "display_only"`. New files must not import `communication.dayuwriter`, open a serial port, expose a motion endpoint, or provide a movement button.
- Printing is at 100% only. The printed 100 mm scale bar must measure 100 mm.
- Keep existing dashboard `--calibration` and `--camera-xyz-only` behavior unchanged.

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `environment/dayuwriter-control.yml` | Declares OpenCV contrib. |
| `vision/realsense/aruco_reference_board.py` | Board geometry, board registration records, and A4 SVG generator. |
| `vision/realsense/aruco_plane_calibration.py` | Corner detection, aggregation, fit, and held-out validation. |
| `vision/realsense/live_red_target_dashboard.py` | Loopback registration UI, live tracker, and marker overlay state. |
| `tests/realsense/test_aruco_reference_board.py` | Board and SVG tests. |
| `tests/realsense/test_aruco_plane_calibration.py` | Synthetic mapping and threshold tests. |
| `tests/realsense/test_live_red_target_dashboard.py` | HTTP, state, and no-motion tests. |
| `docs/dayuwriter/13-a4-aruco-reference-board.md` | Physical procedure and recovery guide. |
| `docs/dayuwriter/reference-board/a4-aruco-v1.svg` | Generated print artifact. |

### Task 1: Board Geometry, Dependency, and Print Artifact

**Files:**
- Modify: `environment/dayuwriter-control.yml`
- Create: `vision/realsense/aruco_reference_board.py`
- Create: `tests/realsense/test_aruco_reference_board.py`
- Create: `docs/dayuwriter/reference-board/a4-aruco-v1.svg`

**Interfaces:**
- Produces `ArucoBoardLayout`, `MarkerDefinition`, `BoardRegistrationError`, `default_layout()`, `render_a4_svg(layout)`, `write_reference_board(path, layout)`, `build_registration_record(layout, captured_at_utc)`, and `load_registration(path, layout)`.
- Task 2 consumes marker corners in machine coordinates. Task 3 consumes registration records.

- [ ] **Step 1: Add and verify the binary OpenCV dependency**

Modify the pip list in `environment/dayuwriter-control.yml`:

```yaml
  - pip:
      - numpy>=2.0
      - pyrealsense2>=2.58
      - opencv-contrib-python>=4.13,<4.14
```

Run:

```powershell
conda activate dayuwriter-control
python -m pip install --only-binary=:all: "opencv-contrib-python>=4.13,<4.14"
python -c "import cv2; assert hasattr(cv2, 'aruco'); print(cv2.__version__)"
```

Expected: the last command prints an OpenCV version and exits 0.

- [ ] **Step 2: Write the failing geometry tests**

Create `tests/realsense/test_aruco_reference_board.py`:

```python
from pathlib import Path

import pytest

from vision.realsense.aruco_reference_board import (
    A4_HEIGHT_MM,
    A4_WIDTH_MM,
    BOARD_REVISION,
    BoardRegistrationError,
    build_registration_record,
    default_layout,
    load_registration,
    render_a4_svg,
    write_reference_board,
)


def test_layout_has_exact_geometry_and_six_non_overlapping_markers() -> None:
    layout = default_layout()

    assert (layout.width_mm, layout.height_mm) == (A4_WIDTH_MM, A4_HEIGHT_MM)
    assert layout.revision == BOARD_REVISION
    assert [marker.identifier for marker in layout.markers] == [0, 1, 2, 3, 4, 5]
    assert layout.marker_size_mm == 40.0
    assert layout.p0_board_xy_mm == pytest.approx((148.5, 105.0))
    assert layout.machine_xy_for_board((148.5, 105.0)) == pytest.approx((0.0, 0.0))
    assert len(layout.marker_corner_machine_xy(0)) == 4
    for first in layout.markers:
        for second in layout.markers:
            if first.identifier < second.identifier:
                assert not first.bounds.intersects(second.bounds)


def test_svg_is_exact_a4_and_has_scale_bar_and_six_markers(tmp_path: Path) -> None:
    layout = default_layout()
    svg = render_a4_svg(layout)
    output = tmp_path / "a4-aruco-v1.svg"

    write_reference_board(output, layout)

    assert 'width="297mm"' in svg
    assert 'height="210mm"' in svg
    assert "100 mm verification scale" in svg
    assert svg.count("data:image/png;base64,") == 6
    assert output.read_text(encoding="utf-8") == svg


def test_registration_rejects_wrong_revision(tmp_path: Path) -> None:
    path = tmp_path / "registration.json"
    path.write_text('{"board_revision":"wrong","operator_confirmed":true}', encoding="utf-8")

    with pytest.raises(BoardRegistrationError, match="board revision"):
        load_registration(path, default_layout())


def test_registration_record_is_display_only() -> None:
    record = build_registration_record(default_layout(), "2026-07-28T12:00:00Z")

    assert record["motion_permission"] == "display_only"
    assert record["operator_confirmed"] is True
    assert record["board"]["p0_machine_xy_mm"] == {"x": 0.0, "y": 0.0}
```

- [ ] **Step 3: Run the test to prove the new module is missing**

Run:

```powershell
python -m pytest tests/realsense/test_aruco_reference_board.py -q
```

Expected: collection fails with `ModuleNotFoundError` for `aruco_reference_board`.

- [ ] **Step 4: Implement board and registration contracts**

Create `vision/realsense/aruco_reference_board.py` with this public model:

```python
A4_WIDTH_MM = 297.0
A4_HEIGHT_MM = 210.0
BOARD_REVISION = "a4-aruco-v1"
ARUCO_DICTIONARY_NAME = "DICT_4X4_50"
FIT_MARKER_IDS = frozenset({0, 1, 3, 4})
VALIDATION_MARKER_IDS = frozenset({2, 5})


@dataclass(frozen=True)
class MarkerBounds:
    left_mm: float
    top_mm: float
    right_mm: float
    bottom_mm: float

    def intersects(self, other: "MarkerBounds") -> bool:
        return not (
            self.right_mm <= other.left_mm
            or other.right_mm <= self.left_mm
            or self.bottom_mm <= other.top_mm
            or other.bottom_mm <= self.top_mm
        )


@dataclass(frozen=True)
class MarkerDefinition:
    identifier: int
    center_board_xy_mm: tuple[float, float]
    size_mm: float

    @property
    def bounds(self) -> MarkerBounds:
        half = self.size_mm / 2.0
        x, y = self.center_board_xy_mm
        return MarkerBounds(x - half, y - half, x + half, y + half)


@dataclass(frozen=True)
class ArucoBoardLayout:
    revision: str
    width_mm: float
    height_mm: float
    p0_board_xy_mm: tuple[float, float]
    marker_size_mm: float
    markers: tuple[MarkerDefinition, ...]

    def marker_corner_machine_xy(self, identifier: int) -> tuple[tuple[float, float], ...]:
        marker = next(item for item in self.markers if item.identifier == identifier)
        half = marker.size_mm / 2.0
        x, y = marker.center_board_xy_mm
        corners = ((x-half, y-half), (x+half, y-half), (x+half, y+half), (x-half, y+half))
        return tuple(self.machine_xy_for_board(point) for point in corners)

    def machine_xy_for_board(self, board_xy_mm: tuple[float, float]) -> tuple[float, float]:
        return (
            board_xy_mm[0] - self.p0_board_xy_mm[0],
            board_xy_mm[1] - self.p0_board_xy_mm[1],
        )
```

Use marker centers `(25,25)`, `(272,25)`, `(272,105)`, `(272,185)`, `(25,185)`, and `(25,105)`. Generate each canonical marker with `cv2.aruco.getPredefinedDictionary` and `cv2.aruco.generateImageMarker`, embed it as a 40 mm SVG image, and add a P0 cross, X+/Y+ arrows, marker IDs, revision, dictionary name, and a labeled 100 mm scale bar. The registration JSON contains schema version 1, board revision, P0 machine XY `(0,0)`, confirmation, UTC timestamp, and display-only permission. Reject malformed, unconfirmed, wrong-revision, or non-display-only registration JSON.

- [ ] **Step 5: Run tests and write the committed SVG**

Run:

```powershell
python -m pytest tests/realsense/test_aruco_reference_board.py -q
python -m vision.realsense.aruco_reference_board --output docs/dayuwriter/reference-board/a4-aruco-v1.svg
python -m pytest tests/realsense/test_aruco_reference_board.py -q
```

Expected: all tests pass and the SVG exists.

- [ ] **Step 6: Commit Task 1**

```powershell
git add environment/dayuwriter-control.yml vision/realsense/aruco_reference_board.py tests/realsense/test_aruco_reference_board.py docs/dayuwriter/reference-board/a4-aruco-v1.svg
git commit -m "feat: add deterministic A4 ArUco reference board"
```

### Task 2: Marker-Corner Mapping and Held-Out Session Validation

**Files:**
- Create: `vision/realsense/aruco_plane_calibration.py`
- Create: `tests/realsense/test_aruco_plane_calibration.py`
- Reuse without behavior changes: `vision/realsense/plane_mapping.py`

**Interfaces:**
- Consumes `ArucoBoardLayout`, `FIT_MARKER_IDS`, `VALIDATION_MARKER_IDS`, `CalibrationPoint`, `fit_pixel_to_machine`, and `predict_machine_xy`.
- Produces `SessionCalibrationError`, `ArucoSessionResult`, `detect_marker_corners(rgb, layout)`, `median_marker_corners(frames, required_ids)`, and `build_aruco_session_record(...)`.
- Task 3 calls the detection and record functions.

- [ ] **Step 1: Write the failing held-out mapping tests**

Create `tests/realsense/test_aruco_plane_calibration.py`:

```python
import numpy as np
import pytest

from vision.realsense.aruco_plane_calibration import (
    SessionCalibrationError,
    build_aruco_session_record,
    median_marker_corners,
)
from vision.realsense.aruco_reference_board import default_layout


def project(matrix: np.ndarray, xy: tuple[float, float]) -> tuple[float, float]:
    result = matrix @ np.array([xy[0], xy[1], 1.0])
    return tuple((result[:2] / result[2]).tolist())


def complete_frames() -> list[dict[int, np.ndarray]]:
    layout = default_layout()
    machine_to_pixel = np.array(
        [[1.7, 0.15, 240.0], [0.12, 1.35, 130.0], [0.0004, -0.0003, 1.0]]
    )
    frame = {
        marker_id: np.asarray(
            [project(machine_to_pixel, point) for point in layout.marker_corner_machine_xy(marker_id)]
        )
        for marker_id in range(6)
    }
    return [frame.copy() for _ in range(12)]


def test_record_uses_held_out_markers_and_is_display_only() -> None:
    result = build_aruco_session_record(
        serial="231122070403",
        frame_size=(640, 480),
        layout=default_layout(),
        complete_frames=complete_frames(),
        captured_at_utc="2026-07-28T12:00:00Z",
    )

    assert result.record["motion_permission"] == "display_only"
    assert result.record["fit_marker_ids"] == [0, 1, 3, 4]
    assert result.record["validation_marker_ids"] == [2, 5]
    assert result.record["validation"]["max_error_mm"] == pytest.approx(0.0, abs=1e-8)


def test_record_rejects_fewer_than_12_complete_frames() -> None:
    with pytest.raises(SessionCalibrationError, match="12 complete frames"):
        build_aruco_session_record(
            serial="231122070403",
            frame_size=(640, 480),
            layout=default_layout(),
            complete_frames=complete_frames()[:11],
            captured_at_utc="2026-07-28T12:00:00Z",
        )


def test_record_rejects_excessive_held_out_error() -> None:
    frames = complete_frames()
    frames[0][2] = frames[0][2] + np.array([8.0, -4.0])

    with pytest.raises(SessionCalibrationError, match="held-out"):
        build_aruco_session_record(
            serial="231122070403",
            frame_size=(640, 480),
            layout=default_layout(),
            complete_frames=frames,
            captured_at_utc="2026-07-28T12:00:00Z",
        )


def test_median_is_per_marker_and_corner() -> None:
    a = {0: np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]])}
    b = {0: a[0] + 2.0}
    c = {0: a[0] + 4.0}

    assert median_marker_corners([a, b, c], {0})[0] == pytest.approx(b[0])
```

- [ ] **Step 2: Run the test to prove the module is missing**

Run:

```powershell
python -m pytest tests/realsense/test_aruco_plane_calibration.py -q
```

Expected: collection fails with `ModuleNotFoundError` for `aruco_plane_calibration`.

- [ ] **Step 3: Implement detection, aggregation, and validation**

Create `vision/realsense/aruco_plane_calibration.py`:

```python
@dataclass(frozen=True)
class ArucoSessionResult:
    record: dict[str, Any]
    matrix_pixel_to_machine: np.ndarray
    median_corners_uv: dict[int, np.ndarray]


def detect_marker_corners(rgb: np.ndarray, layout: ArucoBoardLayout) -> dict[int, np.ndarray]:
    "Return expected marker ID to clockwise finite (4, 2) RGB pixel corners."


def median_marker_corners(
    complete_frames: Sequence[Mapping[int, np.ndarray]],
    required_ids: AbstractSet[int],
) -> dict[int, np.ndarray]:
    "Return per-ID, per-corner medians after shape and finiteness checks."


def build_aruco_session_record(
    *,
    serial: str,
    frame_size: tuple[int, int],
    layout: ArucoBoardLayout,
    complete_frames: Sequence[Mapping[int, np.ndarray]],
    captured_at_utc: str,
    mean_error_limit_mm: float = 1.5,
    max_error_limit_mm: float = 3.0,
) -> ArucoSessionResult:
    "Fit IDs 0/1/3/4; validate IDs 2/5; never grant motion."
```

Use `cv2.aruco.detectMarkers` with the named dictionary. Require RGB shape, exact `(640,480)` frame size, a non-empty serial, exactly 12 frames containing IDs 0 through 5, and finite `(4,2)` clockwise corner arrays. Convert each corner to a unique `CalibrationPoint` ID of the form `marker-{id}-corner-{index}`. Use existing `fit_pixel_to_machine` for fit IDs and `predict_machine_xy` for held-out errors. Serialize stream configuration, board revision, IDs, median corners, matrix, point errors, limits, and display-only permission. Raise `SessionCalibrationError` on every rejected precondition or threshold breach.

- [ ] **Step 4: Run focused calibration regression tests**

Run:

```powershell
python -m pytest tests/realsense/test_aruco_plane_calibration.py tests/realsense/test_plane_mapping.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 2**

```powershell
git add vision/realsense/aruco_plane_calibration.py tests/realsense/test_aruco_plane_calibration.py
git commit -m "feat: add ArUco display calibration records"
```

### Task 3: Reference Tracker and Loopback Registration

**Files:**
- Modify: `vision/realsense/live_red_target_dashboard.py`
- Modify: `tests/realsense/test_red_target.py`
- Create: `tests/realsense/test_live_red_target_dashboard.py`

**Interfaces:**
- Consumes Task 1 registration and Task 2 marker observations.
- Produces `ReferenceStatus`, `ArucoReferenceTracker`, `reference_snapshot_state`, and loopback-only `POST /register-board`.
- Task 4 reads state JSON in the browser.

- [ ] **Step 1: Write failing runtime-state tests**

Create `tests/realsense/test_live_red_target_dashboard.py`:

```python
import numpy as np

from vision.realsense.live_red_target_dashboard import (
    ArucoReferenceTracker,
    reference_snapshot_state,
)
from vision.realsense.aruco_reference_board import default_layout


def all_markers() -> dict[int, np.ndarray]:
    return {
        marker_id: np.array(
            [[10.0 + marker_id, 20.0], [20.0 + marker_id, 20.0],
             [20.0 + marker_id, 30.0], [10.0 + marker_id, 30.0]]
        )
        for marker_id in range(6)
    }


def test_tracker_requires_physical_registration() -> None:
    status = ArucoReferenceTracker(layout=default_layout(), registration=None).update(all_markers())

    assert status.state == "registration_required"
    assert status.matrix_pixel_to_machine is None


def test_tracker_drops_mapping_when_a_marker_is_missing() -> None:
    tracker = ArucoReferenceTracker(
        layout=default_layout(),
        registration={"operator_confirmed": True, "motion_permission": "display_only"},
    )
    missing = all_markers()
    missing.pop(5)

    assert tracker.update(missing).state == "reference_lost"
    assert tracker.update(missing).matrix_pixel_to_machine is None


def test_reference_state_is_always_display_only() -> None:
    state = reference_snapshot_state(
        state="calibration_rejected",
        detail="held-out maximum error 4.0 mm exceeds 3.0 mm",
        marker_corners={},
        validation=None,
    )

    assert state["motion_permission"] == "display_only"
    assert state["reference"]["state"] == "calibration_rejected"
    assert "machine_xy_mm" not in state
```

- [ ] **Step 2: Run the new test to verify it fails**

Run:

```powershell
python -m pytest tests/realsense/test_live_red_target_dashboard.py -q
```

Expected: collection fails because tracker symbols do not exist.

- [ ] **Step 3: Add the tracker and preserve existing modes**

Add these contracts to `vision/realsense/live_red_target_dashboard.py`:

```python
@dataclass(frozen=True)
class ReferenceStatus:
    state: str
    detail: str | None
    marker_corners_uv: dict[int, tuple[tuple[float, float], ...]]
    matrix_pixel_to_machine: np.ndarray | None
    validation: dict[str, Any] | None


class ArucoReferenceTracker:
    def __init__(
        self,
        *,
        layout: ArucoBoardLayout,
        registration: dict[str, Any] | None,
        serial: str = "231122070403",
    ) -> None: ...

    def update(self, corners_uv: Mapping[int, np.ndarray]) -> ReferenceStatus: ...
```

Before 12 complete six-marker frames, return `collecting_reference_frames` and no matrix. On frame 12, call `build_aruco_session_record`. Store matrix only for `ready`. A later missing marker, bad shape, or failed re-fit returns `reference_lost` or `calibration_rejected` and clears the matrix. Never retain stale coordinates.

Add `--aruco-reference-board` and `--reference-registration` arguments. The board flag is mutually exclusive with `--camera-xyz-only` and does not alter legacy manual calibration when absent. Add local `POST /register-board` accepting exactly `{"operator_confirmed": true}`. It writes a Task 1 registration artifact and rejects any other JSON object with HTTP 400. No endpoint accepts ports, G-code, axis values, or motion fields.

- [ ] **Step 4: Integrate live reference status with red target output**

In the camera worker, detect marker corners on every RGB frame, update tracker state, and pass a mapping to `observe_target` only when reference state is `ready`. Serialize:

```python
"reference": {
    "state": reference.state,
    "detail": reference.detail,
    "visible_marker_ids": sorted(reference.marker_corners_uv),
    "validation": reference.validation,
},
"motion_permission": "display_only",
```

When the reference is unavailable, retain RGB, red target, depth, and camera XYZ output but omit `machine_xy_mm`.

- [ ] **Step 5: Run runtime regression tests**

Run:

```powershell
python -m pytest tests/realsense/test_live_red_target_dashboard.py tests/realsense/test_red_target.py tests/realsense/test_aruco_plane_calibration.py -q
```

Expected: all tests pass, including legacy camera-XYZ-only and manual-calibration tests.

- [ ] **Step 6: Commit Task 3**

```powershell
git add vision/realsense/live_red_target_dashboard.py tests/realsense/test_red_target.py tests/realsense/test_live_red_target_dashboard.py
git commit -m "feat: track ArUco reference board in dashboard"
```

### Task 4: Browser Wizard, Guide, and Acceptance Verification

**Files:**
- Modify: `vision/realsense/live_red_target_dashboard.py`
- Modify: `tests/realsense/test_live_red_target_dashboard.py`
- Create: `docs/dayuwriter/13-a4-aruco-reference-board.md`

**Interfaces:**
- Consumes board SVG, registration endpoint, and reference status from Tasks 1 through 3.
- Produces a local operator flow that can register a physically aligned board but cannot move the writer.

- [ ] **Step 1: Write failing wizard and endpoint tests**

Append these to `tests/realsense/test_live_red_target_dashboard.py`:

```python
from vision.realsense.live_red_target_dashboard import _html_page


def test_wizard_has_registration_instruction_and_no_motion_controls() -> None:
    page = _html_page()

    assert "Reference board registration" in page
    assert "I aligned P0, X+30 mm, and Y+30 mm" in page
    assert "Register board" in page
    assert "No GRBL motion is available in this page." in page
    assert "G0" not in page
    assert "$J" not in page
```

Add an HTTP fixture that POSTs `{"operator_confirmed":true}` to `/register-board` and verifies HTTP 200 plus a written display-only record. POST `{"x":10}` and assert HTTP 400.

- [ ] **Step 2: Run the wizard test to verify it fails**

Run:

```powershell
python -m pytest tests/realsense/test_live_red_target_dashboard.py -q
```

Expected: the new HTML and endpoint assertions fail.

- [ ] **Step 3: Build the local registration and status UI**

Extend `_html_page()` with the following HTML:

```html
<section id="reference-registration">
  <h2>Reference board registration</h2>
  <label><input id="registration-confirmation" type="checkbox">
    I aligned P0, X+30 mm, and Y+30 mm, and secured the board.</label>
  <button id="register-board" type="button">Register board</button>
</section>
<section id="reference-status">
  <h2>Reference board</h2>
  <pre id="reference-state">starting</pre>
</section>
```

Disable the button until the checkbox is selected. The click handler sends only `{"operator_confirmed":true}` to the loopback endpoint. Render visible IDs, reference state, and held-out mean/max errors from state JSON. Use an SVG overlay to draw four-corner marker polygons: green for ready, amber while collecting, red for lost or rejected. Preserve the red bounding box and the no-motion statement.

- [ ] **Step 4: Add the operator guide**

Create `docs/dayuwriter/13-a4-aruco-reference-board.md` with these commands and rules:

```markdown
# A4 ArUco Reference Board

## Print and Mount
Print docs/dayuwriter/reference-board/a4-aruco-v1.svg at 100% scale. Measure the 100 mm scale bar; do not use the board when it does not measure 100 mm.

## Register the Board to P0
With a clear pen tip and safe workspace, align printed P0 to physical P0. Use the existing bounded console to check the printed X+30 mm and Y+30 mm crosses, secure the rigid backing, then use the local Register board button. This confirms geometry only and does not move the machine.

## Start Camera A
~~~powershell
conda activate dayuwriter-control
python -m vision.realsense.live_red_target_dashboard --serial 231122070403 --aruco-reference-board --reference-registration docs/dayuwriter/calibration/camera-a-a4-aruco-registration.json --port 8765
~~~

## Interpret the Result
ready with held-out mean <= 1.5 mm and maximum <= 3.0 mm permits XY display only. collecting_reference_frames, reference_lost, and calibration_rejected do not provide a valid machine coordinate.

## Transport and Re-mount
Keep the board secured to the writer. After camera A is re-mounted, run the same command and wait for ready. Re-register only after the board/P0 relationship changed.
```

State explicitly that moving the red target does not require calibration and that targets above the board plane require the later 3D stage.

- [ ] **Step 5: Run full offline verification and static safety check**

Run:

```powershell
python -m pytest -q -p no:cacheprovider --basetemp "$env:USERPROFILE\pytest-temp\dayuwriter-aruco-tests"
python -m py_compile vision/realsense/aruco_reference_board.py vision/realsense/aruco_plane_calibration.py vision/realsense/live_red_target_dashboard.py
rg -n "communication\.dayuwriter|serial\.Serial|\$J|G0|G1" vision/realsense/aruco_reference_board.py vision/realsense/aruco_plane_calibration.py vision/realsense/live_red_target_dashboard.py
```

Expected: all tests and compilation pass; the final search has no output.

- [ ] **Step 6: Run the physical display-only acceptance sequence**

1. Print at 100%, measure the scale bar, mount the board on rigid backing, and complete the P0/X+/Y+ alignment.
2. Start the board mode dashboard and wait for `ready`.
3. Place the red square at two known central positions; record displayed XY and session artifact.
4. Re-mount camera A without moving the board; start a new session and repeat step 3.
5. Do not issue GRBL commands from the dashboard. Any later physical movement remains a separate task.

Expected: two display-only records contain measured validation errors; the dashboard exposes no motion control.

- [ ] **Step 7: Commit Task 4**

```powershell
git add vision/realsense/live_red_target_dashboard.py tests/realsense/test_live_red_target_dashboard.py docs/dayuwriter/13-a4-aruco-reference-board.md
git commit -m "feat: add display-only ArUco calibration wizard"
```

## Plan Self-Review

### Spec Coverage

- Board geometry, P0, scale check, and printable artifact: Task 1.
- One-time board-to-P0 physical registration: Tasks 1, 3, and 4.
- 90-frame warmup, 12-frame automatic camera-A session: Tasks 2 and 3.
- Four fit markers, two held-out markers, and explicit quality limits: Task 2.
- Runtime reference loss, no stale mapping, and visual state: Task 3.
- Browser workflow, no-motion UI, guide, test suite, and physical acceptance: Task 4.

### Consistency Check

Task 1 owns the board coordinate convention. Task 2 turns that convention into a validated matrix. Task 3 clears the matrix whenever marker quality fails. Task 4 only visualizes Task 3 state; it adds no serial or movement path.

### Forbidden Marker Scan

All task steps name concrete files, public functions, code snippets, tests, commands, expected outcomes, and commits.
