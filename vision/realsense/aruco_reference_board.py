"""Deterministic A4 ArUco reference board and display-only registration records."""

from __future__ import annotations

import argparse
import base64
import json
from dataclasses import dataclass
from pathlib import Path

import cv2


A4_WIDTH_MM = 297.0
A4_HEIGHT_MM = 210.0
BOARD_REVISION = "a4-aruco-v2"
ARUCO_DICTIONARY_NAME = "DICT_4X4_50"
FIT_MARKER_IDS = frozenset({0, 1, 3, 4})
VALIDATION_MARKER_IDS = frozenset({2, 5})


class BoardRegistrationError(ValueError):
    """Raised when a reference-board registration is malformed or unsafe to use."""


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
        half_size = self.size_mm / 2.0
        center_x, center_y = self.center_board_xy_mm
        return MarkerBounds(
            center_x - half_size,
            center_y - half_size,
            center_x + half_size,
            center_y + half_size,
        )


@dataclass(frozen=True)
class ArucoBoardLayout:
    revision: str
    width_mm: float
    height_mm: float
    p0_board_xy_mm: tuple[float, float]
    marker_size_mm: float
    markers: tuple[MarkerDefinition, ...]

    def marker_corner_board_xy(self, identifier: int) -> tuple[tuple[float, float], ...]:
        bounds = self._marker(identifier).bounds
        return (
            (bounds.left_mm, bounds.top_mm),
            (bounds.right_mm, bounds.top_mm),
            (bounds.right_mm, bounds.bottom_mm),
            (bounds.left_mm, bounds.bottom_mm),
        )

    def marker_corner_machine_xy(self, identifier: int) -> tuple[tuple[float, float], ...]:
        return tuple(
            self.machine_xy_for_board(point) for point in self.marker_corner_board_xy(identifier)
        )

    def machine_xy_for_board(self, board_xy_mm: tuple[float, float]) -> tuple[float, float]:
        """Map SVG paper coordinates to the writer's Cartesian P0 frame.

        SVG Y increases downward on the printed page; the writer's verified Y+
        direction is upward from P0 in the paper coordinate convention.
        """
        return (
            float(board_xy_mm[0] - self.p0_board_xy_mm[0]),
            float(self.p0_board_xy_mm[1] - board_xy_mm[1]),
        )

    def _marker(self, identifier: int) -> MarkerDefinition:
        for marker in self.markers:
            if marker.identifier == identifier:
                return marker
        raise BoardRegistrationError(f"unknown marker id: {identifier}")


def default_layout() -> ArucoBoardLayout:
    """Return the fixed physical layout for revision ``a4-aruco-v2``."""
    marker_size_mm = 40.0
    marker_centers = ((25.0, 25.0), (272.0, 25.0), (272.0, 105.0), (272.0, 185.0), (25.0, 185.0), (25.0, 105.0))
    return ArucoBoardLayout(
        revision=BOARD_REVISION,
        width_mm=A4_WIDTH_MM,
        height_mm=A4_HEIGHT_MM,
        p0_board_xy_mm=(148.5, 105.0),
        marker_size_mm=marker_size_mm,
        markers=tuple(
            MarkerDefinition(identifier, center, marker_size_mm)
            for identifier, center in enumerate(marker_centers)
        ),
    )


def render_a4_svg(layout: ArucoBoardLayout) -> str:
    """Render a physical-size SVG that must be printed at 100 percent scale."""
    if layout.revision != BOARD_REVISION:
        raise BoardRegistrationError(f"unsupported board revision: {layout.revision}")
    marker_elements = "\n".join(_svg_marker(marker) for marker in layout.markers)
    p0_x, p0_y = layout.p0_board_xy_mm
    x_plus_30_x = p0_x + 30.0
    y_plus_30_y = p0_y - 30.0
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{layout.width_mm:g}mm" height="{layout.height_mm:g}mm" viewBox="0 0 {layout.width_mm:g} {layout.height_mm:g}">
  <rect x="0" y="0" width="{layout.width_mm:g}" height="{layout.height_mm:g}" fill="white"/>
  <text x="{p0_x:g}" y="10" font-family="Arial, sans-serif" font-size="5" text-anchor="middle">{layout.revision} | {ARUCO_DICTIONARY_NAME} | print at 100%</text>
  {marker_elements}
  <g id="p0-cross" stroke="#12532b" stroke-width="0.8" fill="none">
    <line x1="{p0_x - 6:g}" y1="{p0_y:g}" x2="{p0_x + 6:g}" y2="{p0_y:g}"/>
    <line x1="{p0_x:g}" y1="{p0_y - 6:g}" x2="{p0_x:g}" y2="{p0_y + 6:g}"/>
  </g>
  <g id="x-plus-30-cross" stroke="#12532b" stroke-width="0.8" fill="none">
    <line x1="{x_plus_30_x - 4:g}" y1="{p0_y:g}" x2="{x_plus_30_x + 4:g}" y2="{p0_y:g}"/>
    <line x1="{x_plus_30_x:g}" y1="{p0_y - 4:g}" x2="{x_plus_30_x:g}" y2="{p0_y + 4:g}"/>
  </g>
  <g id="y-plus-30-cross" stroke="#12532b" stroke-width="0.8" fill="none">
    <line x1="{p0_x - 4:g}" y1="{y_plus_30_y:g}" x2="{p0_x + 4:g}" y2="{y_plus_30_y:g}"/>
    <line x1="{p0_x:g}" y1="{y_plus_30_y - 4:g}" x2="{p0_x:g}" y2="{y_plus_30_y + 4:g}"/>
  </g>
  <g stroke="#12532b" stroke-width="0.8" fill="none">
    <line x1="{p0_x + 8:g}" y1="{p0_y:g}" x2="{p0_x + 28:g}" y2="{p0_y:g}"/>
    <line x1="{p0_x:g}" y1="{p0_y - 8:g}" x2="{p0_x:g}" y2="{p0_y - 28:g}"/>
  </g>
  <g fill="#12532b" font-family="Arial, sans-serif" font-size="4">
    <text x="{x_plus_30_x + 6:g}" y="{p0_y + 1.5:g}">X+30 mm</text>
    <text x="{p0_x + 6:g}" y="{y_plus_30_y + 2:g}">Y+30 mm</text>
    <text x="{p0_x + 8:g}" y="{p0_y - 8:g}">P0</text>
  </g>
  <g stroke="black" stroke-width="0.8" fill="none">
    <line x1="98.5" y1="195" x2="198.5" y2="195"/>
    <line x1="98.5" y1="192" x2="98.5" y2="198"/>
    <line x1="198.5" y1="192" x2="198.5" y2="198"/>
  </g>
  <text x="148.5" y="202" font-family="Arial, sans-serif" font-size="4" text-anchor="middle">100 mm verification scale</text>
</svg>
'''


def write_reference_board(path: Path, layout: ArucoBoardLayout) -> None:
    """Write the deterministic SVG artifact for printing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_a4_svg(layout), encoding="utf-8")


def build_registration_record(layout: ArucoBoardLayout, captured_at_utc: str) -> dict[str, object]:
    """Build the operator-confirmed board-to-P0 registration record."""
    timestamp = _validated_timestamp(captured_at_utc)
    return {
        "schema_version": 1,
        "captured_at_utc": timestamp,
        "board_revision": layout.revision,
        "operator_confirmed": True,
        "board": {
            "width_mm": layout.width_mm,
            "height_mm": layout.height_mm,
            "p0_board_xy_mm": {"x": layout.p0_board_xy_mm[0], "y": layout.p0_board_xy_mm[1]},
            "p0_machine_xy_mm": {"x": 0.0, "y": 0.0},
        },
        "motion_permission": "display_only",
    }


def load_registration(path: Path, layout: ArucoBoardLayout) -> dict[str, object]:
    """Load a confirmed registration only when it matches the exact board revision."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BoardRegistrationError(f"cannot read board registration: {path}") from exc
    if not isinstance(payload, dict):
        raise BoardRegistrationError("board registration must be a JSON object")
    if payload.get("board_revision") != layout.revision:
        raise BoardRegistrationError("board registration board revision does not match")
    if payload.get("operator_confirmed") is not True:
        raise BoardRegistrationError("board registration requires operator confirmation")
    if payload.get("motion_permission") != "display_only":
        raise BoardRegistrationError("board registration must be display_only")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate the DayuWriter A4 ArUco reference board.")
    parser.add_argument("--output", required=True, type=Path, help="A4 SVG output path")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    write_reference_board(args.output, default_layout())
    print(f"A4 ArUco reference board written to {args.output}")
    return 0


def _svg_marker(marker: MarkerDefinition) -> str:
    image_base64 = _marker_png_base64(marker.identifier)
    bounds = marker.bounds
    return f'''<g>
    <image x="{bounds.left_mm:g}" y="{bounds.top_mm:g}" width="{marker.size_mm:g}" height="{marker.size_mm:g}" href="data:image/png;base64,{image_base64}"/>
    <text x="{marker.center_board_xy_mm[0]:g}" y="{bounds.bottom_mm + 4:g}" font-family="Arial, sans-serif" font-size="4" text-anchor="middle">ID {marker.identifier}</text>
  </g>'''


def _marker_png_base64(identifier: int) -> str:
    dictionary_id = getattr(cv2.aruco, ARUCO_DICTIONARY_NAME)
    dictionary = cv2.aruco.getPredefinedDictionary(dictionary_id)
    image = cv2.aruco.generateImageMarker(dictionary, identifier, 480)
    success, encoded = cv2.imencode(".png", image)
    if not success:
        raise BoardRegistrationError(f"cannot encode marker id {identifier}")
    return base64.b64encode(encoded.tobytes()).decode("ascii")


def _validated_timestamp(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BoardRegistrationError("captured_at_utc must be a non-empty string")
    return value.strip()


if __name__ == "__main__":
    raise SystemExit(main())
