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
    assert BOARD_REVISION == "a4-aruco-v3"
    assert layout.revision == BOARD_REVISION
    assert [marker.identifier for marker in layout.markers] == [0, 1, 2, 3, 4, 5]
    assert layout.marker_size_mm == 40.0
    assert layout.p0_board_xy_mm == pytest.approx((148.5, 105.0))
    assert layout.machine_xy_for_board((148.5, 105.0)) == pytest.approx((0.0, 0.0))
    assert layout.machine_xy_for_board((178.5, 105.0)) == pytest.approx((30.0, 0.0))
    assert layout.machine_xy_for_board((148.5, 75.0)) == pytest.approx((0.0, 30.0))
    assert len(layout.marker_corner_machine_xy(0)) == 4
    for first in layout.markers:
        for second in layout.markers:
            if first.identifier < second.identifier:
                assert not first.bounds.intersects(second.bounds)


def test_layout_keeps_all_markers_inside_a_12_mm_print_safe_margin() -> None:
    layout = default_layout()

    assert min(marker.bounds.left_mm for marker in layout.markers) >= 12.0
    assert min(marker.bounds.top_mm for marker in layout.markers) >= 12.0
    assert max(marker.bounds.right_mm for marker in layout.markers) <= layout.width_mm - 12.0
    assert max(marker.bounds.bottom_mm for marker in layout.markers) <= layout.height_mm - 12.0


def test_svg_is_exact_a4_and_has_scale_bar_and_six_markers(tmp_path: Path) -> None:
    layout = default_layout()
    svg = render_a4_svg(layout)
    output = tmp_path / "a4-aruco-v3.svg"

    write_reference_board(output, layout)

    assert 'width="297mm"' in svg
    assert 'height="210mm"' in svg
    assert "100 mm verification scale" in svg
    assert 'id="p0-cross"' in svg
    assert 'id="x-plus-30-cross"' in svg
    assert 'id="y-plus-30-cross"' in svg
    assert "X+30 mm" in svg
    assert "Y+30 mm" in svg
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
