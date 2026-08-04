"""Deterministic A4 ArUco reference board and display-only registration records."""

from __future__ import annotations

import argparse
import base64
import json
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


A4_WIDTH_MM = 297.0
A4_HEIGHT_MM = 210.0
A4_PNG_DPI = 300.0
A4_PNG_PIXELS_PER_MM = A4_PNG_DPI / 25.4
A4_PNG_WIDTH_PX = round(A4_WIDTH_MM * A4_PNG_PIXELS_PER_MM)
A4_PNG_HEIGHT_PX = round(A4_HEIGHT_MM * A4_PNG_PIXELS_PER_MM)
BOARD_REVISION = "a4-aruco-v3"
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
    """Return the fixed physical layout for revision ``a4-aruco-v3``."""
    marker_size_mm = 40.0
    marker_centers = ((32.0, 32.0), (265.0, 32.0), (265.0, 105.0), (265.0, 178.0), (32.0, 178.0), (32.0, 105.0))
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


def render_a4_png(layout: ArucoBoardLayout) -> bytes:
    """Render the A4 board at 300 DPI with physical-resolution PNG metadata."""
    if layout.revision != BOARD_REVISION:
        raise BoardRegistrationError(f"unsupported board revision: {layout.revision}")
    image = np.full((A4_PNG_HEIGHT_PX, A4_PNG_WIDTH_PX, 3), 255, dtype=np.uint8)
    for marker in layout.markers:
        _draw_png_marker(image, marker)

    p0_x, p0_y = layout.p0_board_xy_mm
    x_plus_30_x = p0_x + 30.0
    y_plus_30_y = p0_y - 30.0
    green = (43, 83, 18)
    black = (0, 0, 0)
    _line_mm(image, (p0_x - 6.0, p0_y), (p0_x + 6.0, p0_y), green)
    _line_mm(image, (p0_x, p0_y - 6.0), (p0_x, p0_y + 6.0), green)
    _line_mm(image, (x_plus_30_x - 4.0, p0_y), (x_plus_30_x + 4.0, p0_y), green)
    _line_mm(image, (x_plus_30_x, p0_y - 4.0), (x_plus_30_x, p0_y + 4.0), green)
    _line_mm(image, (p0_x - 4.0, y_plus_30_y), (p0_x + 4.0, y_plus_30_y), green)
    _line_mm(image, (p0_x, y_plus_30_y - 4.0), (p0_x, y_plus_30_y + 4.0), green)
    _line_mm(image, (p0_x + 8.0, p0_y), (p0_x + 28.0, p0_y), green)
    _line_mm(image, (p0_x, p0_y - 8.0), (p0_x, p0_y - 28.0), green)
    _text_mm(
        image,
        f"{layout.revision} | {ARUCO_DICTIONARY_NAME} | print at 100%",
        (p0_x, 10.0),
        black,
        centered=True,
    )
    _text_mm(image, "P0", (p0_x + 8.0, p0_y - 8.0), green)
    _text_mm(image, "X+30 mm", (x_plus_30_x + 6.0, p0_y + 1.5), green)
    _text_mm(image, "Y+30 mm", (p0_x + 6.0, y_plus_30_y + 2.0), green)
    _line_mm(image, (98.5, 195.0), (198.5, 195.0), black)
    _line_mm(image, (98.5, 192.0), (98.5, 198.0), black)
    _line_mm(image, (198.5, 192.0), (198.5, 198.0), black)
    _text_mm(image, "100 mm verification scale", (148.5, 202.0), black, centered=True)
    success, encoded = cv2.imencode(".png", image)
    if not success:
        raise BoardRegistrationError("cannot encode A4 PNG reference board")
    return _with_png_physical_resolution(encoded.tobytes(), A4_PNG_DPI)


def write_reference_board_png(path: Path, layout: ArucoBoardLayout) -> None:
    """Write the deterministic 300 DPI A4 PNG artifact for printing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render_a4_png(layout))


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
    parser.add_argument("--output", type=Path, help="A4 SVG output path")
    parser.add_argument("--png-output", type=Path, help="300 DPI A4 PNG output path")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.output is None and args.png_output is None:
        raise SystemExit("provide --output for SVG and/or --png-output for PNG")
    layout = default_layout()
    if args.output is not None:
        write_reference_board(args.output, layout)
        print(f"A4 ArUco SVG reference board written to {args.output}")
    if args.png_output is not None:
        write_reference_board_png(args.png_output, layout)
        print(f"A4 ArUco 300 DPI PNG reference board written to {args.png_output}")
    return 0


def _svg_marker(marker: MarkerDefinition) -> str:
    image_base64 = _marker_png_base64(marker.identifier)
    bounds = marker.bounds
    return f'''<g>
    <image x="{bounds.left_mm:g}" y="{bounds.top_mm:g}" width="{marker.size_mm:g}" height="{marker.size_mm:g}" href="data:image/png;base64,{image_base64}"/>
    <text x="{marker.center_board_xy_mm[0]:g}" y="{bounds.bottom_mm + 4:g}" font-family="Arial, sans-serif" font-size="4" text-anchor="middle">ID {marker.identifier}</text>
  </g>'''


def _marker_png_base64(identifier: int) -> str:
    image = _marker_image(identifier, 480)
    success, encoded = cv2.imencode(".png", image)
    if not success:
        raise BoardRegistrationError(f"cannot encode marker id {identifier}")
    return base64.b64encode(encoded.tobytes()).decode("ascii")


def _marker_image(identifier: int, side_px: int) -> np.ndarray:
    dictionary_id = getattr(cv2.aruco, ARUCO_DICTIONARY_NAME)
    dictionary = cv2.aruco.getPredefinedDictionary(dictionary_id)
    return cv2.aruco.generateImageMarker(dictionary, identifier, side_px)


def _draw_png_marker(image: np.ndarray, marker: MarkerDefinition) -> None:
    bounds = marker.bounds
    left, top = _pixel_point((bounds.left_mm, bounds.top_mm))
    right, bottom = _pixel_point((bounds.right_mm, bounds.bottom_mm))
    marker_image = cv2.resize(
        _marker_image(marker.identifier, 480),
        (right - left, bottom - top),
        interpolation=cv2.INTER_NEAREST,
    )
    image[top:bottom, left:right] = cv2.cvtColor(marker_image, cv2.COLOR_GRAY2BGR)
    _text_mm(
        image,
        f"ID {marker.identifier}",
        (marker.center_board_xy_mm[0], bounds.bottom_mm + 4.0),
        (0, 0, 0),
        centered=True,
    )


def _line_mm(
    image: np.ndarray,
    start_mm: tuple[float, float],
    end_mm: tuple[float, float],
    color: tuple[int, int, int],
) -> None:
    cv2.line(
        image,
        _pixel_point(start_mm),
        _pixel_point(end_mm),
        color,
        max(1, round(0.8 * A4_PNG_PIXELS_PER_MM)),
        lineType=cv2.LINE_AA,
    )


def _text_mm(
    image: np.ndarray,
    text: str,
    position_mm: tuple[float, float],
    color: tuple[int, int, int],
    *,
    centered: bool = False,
) -> None:
    point = _pixel_point(position_mm)
    font_scale = 4.0 * A4_PNG_PIXELS_PER_MM / 30.0
    thickness = max(1, round(0.6 * A4_PNG_PIXELS_PER_MM))
    if centered:
        text_size, _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
        point = (point[0] - text_size[0] // 2, point[1])
    cv2.putText(image, text, point, cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness, cv2.LINE_AA)


def _pixel_point(point_mm: tuple[float, float]) -> tuple[int, int]:
    return (round(point_mm[0] * A4_PNG_PIXELS_PER_MM), round(point_mm[1] * A4_PNG_PIXELS_PER_MM))


def _with_png_physical_resolution(png: bytes, dpi: float) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    if not png.startswith(signature):
        raise BoardRegistrationError("encoded reference board is not a PNG")
    ihdr_length = struct.unpack(">I", png[8:12])[0]
    after_ihdr = 8 + 12 + ihdr_length
    pixels_per_meter = round(dpi / 0.0254)
    physical_data = struct.pack(">IIB", pixels_per_meter, pixels_per_meter, 1)
    physical_chunk = (
        struct.pack(">I", len(physical_data))
        + b"pHYs"
        + physical_data
        + struct.pack(">I", zlib.crc32(b"pHYs" + physical_data) & 0xFFFFFFFF)
    )
    return png[:after_ihdr] + physical_chunk + png[after_ihdr:]


def _validated_timestamp(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BoardRegistrationError("captured_at_utc must be a non-empty string")
    return value.strip()


if __name__ == "__main__":
    raise SystemExit(main())
