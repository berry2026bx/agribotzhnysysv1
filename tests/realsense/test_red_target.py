import math

import numpy as np
import pytest

from vision.realsense.red_target import (
    RedTargetConfig,
    find_red_target,
    observe_target,
)
from vision.realsense.live_red_target_dashboard import make_bmp_bytes, snapshot_state


def red_circle_frame(
    *, center_uv: tuple[int, int] = (50, 40), radius_px: int = 12
) -> np.ndarray:
    image = np.zeros((80, 100, 3), dtype=np.uint8)
    vertical, horizontal = np.ogrid[: image.shape[0], : image.shape[1]]
    mask = (horizontal - center_uv[0]) ** 2 + (vertical - center_uv[1]) ** 2 <= radius_px**2
    image[mask] = (245, 15, 10)
    return image


def test_finds_a_saturated_red_circular_target() -> None:
    target = find_red_target(red_circle_frame())

    assert target is not None
    assert target.center_uv == pytest.approx((50.0, 40.0), abs=0.1)
    assert target.area_px > 400


def test_ignores_an_elongated_red_region() -> None:
    image = np.zeros((80, 100, 3), dtype=np.uint8)
    image[25:35, 10:80] = (245, 15, 10)

    assert find_red_target(image) is None


class SparseDepthFrame:
    def get_distance(self, u: int, v: int) -> float:
        if (u, v) == (51, 40):
            return 0.75
        return 0.0


def test_observation_reports_camera_xyz_and_display_only_machine_xy() -> None:
    target = find_red_target(red_circle_frame())
    assert target is not None

    observation = observe_target(
        target,
        depth_frame=SparseDepthFrame(),
        color_intrinsics=object(),
        deproject=lambda intrinsics, pixel, depth: [0.1, 0.2, depth],
        pixel_to_machine=np.array(
            [[1.0, 0.0, -20.0], [0.0, 1.0, -10.0], [0.0, 0.0, 1.0]]
        ),
        width=100,
        height=80,
        depth_sample_radius=1,
    )

    assert observation.target_center_uv == pytest.approx((50.0, 40.0))
    assert observation.depth_sample_uv == (51, 40)
    assert observation.depth_m == pytest.approx(0.75)
    assert observation.camera_xyz_m == pytest.approx((0.1, 0.2, 0.75))
    assert observation.machine_xy_mm == pytest.approx((30.0, 30.0))
    assert math.isfinite(observation.machine_xy_mm[0])


def test_rejects_a_non_rgb_frame() -> None:
    with pytest.raises(ValueError, match="RGB"):
        find_red_target(np.zeros((40, 40), dtype=np.uint8), RedTargetConfig())


def test_dashboard_state_is_ready_but_never_authorizes_motion() -> None:
    target = find_red_target(red_circle_frame())
    assert target is not None
    observation = observe_target(
        target,
        depth_frame=SparseDepthFrame(),
        color_intrinsics=object(),
        deproject=lambda intrinsics, pixel, depth: [0.1, 0.2, depth],
        pixel_to_machine=np.array(
            [[1.0, 0.0, -20.0], [0.0, 1.0, -10.0], [0.0, 0.0, 1.0]]
        ),
        width=100,
        height=80,
        depth_sample_radius=1,
    )

    state = snapshot_state(target, observation, error=None)

    assert state["state"] == "ready"
    assert state["motion_permission"] == "display_only"
    assert state["machine_xy_mm"] == {"x": 30.0, "y": 30.0}


def test_dashboard_bmp_uses_padded_24_bit_rows() -> None:
    rgb = np.zeros((2, 3, 3), dtype=np.uint8)
    rgb[0, 0] = (255, 0, 0)

    bmp = make_bmp_bytes(rgb)

    assert bmp[:2] == b"BM"
    assert int.from_bytes(bmp[2:6], "little") == len(bmp)
