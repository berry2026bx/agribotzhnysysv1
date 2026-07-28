"""Display-only pixel-to-DayuWriter-plane calibration for one fixed camera pose."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np


class PlaneMappingError(ValueError):
    """Raised when planar calibration data cannot support a reliable fit."""


@dataclass(frozen=True)
class CalibrationPoint:
    identifier: str
    pixel_uv: tuple[float, float]
    machine_xy_mm: tuple[float, float]


def fit_pixel_to_machine(points: Sequence[CalibrationPoint]) -> np.ndarray:
    """Fit a projective mapping from image pixel coordinates to machine XY."""
    normalized_points = _validate_points(points, label="fit")
    if len(normalized_points) < 4:
        raise PlaneMappingError("at least four fit points are required")

    rows: list[list[float]] = []
    expected: list[float] = []
    for point in normalized_points:
        u, v = point.pixel_uv
        x, y = point.machine_xy_mm
        rows.extend(
            [
                [u, v, 1.0, 0.0, 0.0, 0.0, -u * x, -v * x],
                [0.0, 0.0, 0.0, u, v, 1.0, -u * y, -v * y],
            ]
        )
        expected.extend([x, y])

    solution, _, rank, _ = np.linalg.lstsq(
        np.asarray(rows, dtype=float), np.asarray(expected, dtype=float), rcond=None
    )
    if int(rank) < 8 or not np.all(np.isfinite(solution)):
        raise PlaneMappingError("fit points are degenerate")

    matrix = np.array(
        [
            [solution[0], solution[1], solution[2]],
            [solution[3], solution[4], solution[5]],
            [solution[6], solution[7], 1.0],
        ],
        dtype=float,
    )
    for point in normalized_points:
        predict_machine_xy(matrix, point.pixel_uv)
    return matrix


def predict_machine_xy(
    matrix_pixel_to_machine: np.ndarray, pixel_uv: tuple[float, float]
) -> tuple[float, float]:
    """Map one RGB pixel to a predicted machine-plane coordinate in mm."""
    matrix = np.asarray(matrix_pixel_to_machine, dtype=float)
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
        raise PlaneMappingError("mapping matrix must be a finite 3x3 array")
    u, v = _finite_pair(pixel_uv, "pixel_uv")
    homogeneous = matrix @ np.array([u, v, 1.0], dtype=float)
    denominator = float(homogeneous[2])
    if not math.isfinite(denominator) or abs(denominator) < 1e-12:
        raise PlaneMappingError("pixel projects to an invalid homogeneous denominator")
    x = float(homogeneous[0] / denominator)
    y = float(homogeneous[1] / denominator)
    if not math.isfinite(x) or not math.isfinite(y):
        raise PlaneMappingError("predicted machine coordinate is non-finite")
    return x, y


def build_calibration_record(
    camera_serial: str,
    fit_points: Sequence[CalibrationPoint],
    validation_points: Sequence[CalibrationPoint],
    *,
    captured_at_utc: str,
) -> dict[str, Any]:
    """Build a versioned display-only calibration artifact with held-out errors."""
    serial = _validate_serial(camera_serial)
    if not isinstance(captured_at_utc, str) or not captured_at_utc.strip():
        raise PlaneMappingError("captured_at_utc must be a non-empty string")
    normalized_fit_points = _validate_points(fit_points, label="fit")
    normalized_validation_points = _validate_points(validation_points, label="validation")
    if not normalized_validation_points:
        raise PlaneMappingError("at least one validation point is required")
    _validate_unique_ids(normalized_fit_points + normalized_validation_points)

    matrix = fit_pixel_to_machine(normalized_fit_points)
    validation_records: list[dict[str, Any]] = []
    errors: list[float] = []
    for point in normalized_validation_points:
        predicted_x, predicted_y = predict_machine_xy(matrix, point.pixel_uv)
        expected_x, expected_y = point.machine_xy_mm
        error_mm = math.hypot(predicted_x - expected_x, predicted_y - expected_y)
        errors.append(error_mm)
        validation_records.append(
            {
                "id": point.identifier,
                "pixel_uv": _pair_record(point.pixel_uv, "u", "v"),
                "expected_machine_xy_mm": _pair_record(
                    point.machine_xy_mm, "x", "y"
                ),
                "predicted_machine_xy_mm": {"x": predicted_x, "y": predicted_y},
                "error_mm": error_mm,
            }
        )

    return {
        "schema_version": 1,
        "captured_at_utc": captured_at_utc.strip(),
        "camera": {"serial": serial},
        "fit_points": [_point_record(point) for point in normalized_fit_points],
        "matrix_pixel_to_machine": matrix.tolist(),
        "validation": {
            "count": len(validation_records),
            "mean_error_mm": float(np.mean(errors)),
            "max_error_mm": float(np.max(errors)),
            "points": validation_records,
        },
        "motion_permission": "display_only",
        "limitations": [
            "The artifact is valid only for this camera serial and unchanged mount pose.",
            "This artifact does not authorize GRBL motion.",
        ],
    }


def load_calibration_input(path: Path) -> tuple[str, list[CalibrationPoint], list[CalibrationPoint]]:
    """Read a user-edited reference-point input file."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlaneMappingError(f"cannot read calibration input: {path}") from exc
    if not isinstance(payload, dict):
        raise PlaneMappingError("calibration input must be a JSON object")
    camera = payload.get("camera")
    if not isinstance(camera, dict):
        raise PlaneMappingError("calibration input requires camera.serial")
    serial = _validate_serial(camera.get("serial"))
    return (
        serial,
        _points_from_records(payload.get("fit_points"), "fit_points"),
        _points_from_records(payload.get("validation_points"), "validation_points"),
    )


def write_calibration_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fit a display-only RGB-pixel to DayuWriter-XY mapping."
    )
    parser.add_argument("--input", required=True, type=Path, help="Reference-point JSON file")
    parser.add_argument("--output", required=True, type=Path, help="Calibration artifact JSON")
    parser.add_argument("--predict-u", type=float, help="Optional RGB pixel u coordinate")
    parser.add_argument("--predict-v", type=float, help="Optional RGB pixel v coordinate")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if (args.predict_u is None) != (args.predict_v is None):
            raise PlaneMappingError("--predict-u and --predict-v must be supplied together")
        serial, fit_points, validation_points = load_calibration_input(args.input)
        captured_at_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        record = build_calibration_record(
            serial, fit_points, validation_points, captured_at_utc=captured_at_utc
        )
        write_calibration_record(args.output, record)
        print(f"Display-only calibration written to {args.output}")
        if args.predict_u is not None:
            predicted_x, predicted_y = predict_machine_xy(
                np.asarray(record["matrix_pixel_to_machine"], dtype=float),
                (args.predict_u, args.predict_v),
            )
            print(
                json.dumps(
                    {
                        "pixel_uv": {"u": args.predict_u, "v": args.predict_v},
                        "predicted_machine_xy_mm": {"x": predicted_x, "y": predicted_y},
                        "motion_permission": "display_only",
                    }
                )
            )
        return 0
    except PlaneMappingError as exc:
        print(f"Plane mapping failed: {exc}")
        return 1


def _validate_points(
    points: Sequence[CalibrationPoint], *, label: str
) -> list[CalibrationPoint]:
    try:
        normalized = list(points)
    except TypeError as exc:
        raise PlaneMappingError(f"{label} points must be iterable") from exc
    for point in normalized:
        if not isinstance(point, CalibrationPoint):
            raise PlaneMappingError(f"{label} points must be CalibrationPoint instances")
        if not isinstance(point.identifier, str) or not point.identifier.strip():
            raise PlaneMappingError(f"{label} point has an invalid id")
        _finite_pair(point.pixel_uv, f"{label} point {point.identifier!r} pixel_uv")
        _finite_pair(point.machine_xy_mm, f"{label} point {point.identifier!r} machine_xy_mm")
    _validate_unique_ids(normalized)
    return normalized


def _validate_unique_ids(points: Sequence[CalibrationPoint]) -> None:
    identifiers = [point.identifier for point in points]
    if len(set(identifiers)) != len(identifiers):
        raise PlaneMappingError("point ids must be unique")


def _validate_serial(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlaneMappingError("camera serial must be a non-empty string")
    return value.strip()


def _finite_pair(value: object, label: str) -> tuple[float, float]:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise PlaneMappingError(f"{label} must contain exactly two finite numbers")
    try:
        first = float(value[0])
        second = float(value[1])
    except (TypeError, ValueError) as exc:
        raise PlaneMappingError(f"{label} must contain exactly two finite numbers") from exc
    if not math.isfinite(first) or not math.isfinite(second):
        raise PlaneMappingError(f"{label} must contain exactly two finite numbers")
    return first, second


def _points_from_records(value: object, label: str) -> list[CalibrationPoint]:
    if not isinstance(value, list):
        raise PlaneMappingError(f"{label} must be a JSON list")
    points: list[CalibrationPoint] = []
    for item in value:
        if not isinstance(item, dict):
            raise PlaneMappingError(f"{label} entries must be JSON objects")
        pixel = item.get("pixel_uv")
        machine = item.get("machine_xy_mm")
        if not isinstance(pixel, dict) or not isinstance(machine, dict):
            raise PlaneMappingError(f"{label} entries require pixel_uv and machine_xy_mm")
        points.append(
            CalibrationPoint(
                str(item.get("id", "")),
                _finite_pair((pixel.get("u"), pixel.get("v")), f"{label} pixel_uv"),
                _finite_pair((machine.get("x"), machine.get("y")), f"{label} machine_xy_mm"),
            )
        )
    return points


def _pair_record(values: tuple[float, float], first_key: str, second_key: str) -> dict[str, float]:
    return {first_key: float(values[0]), second_key: float(values[1])}


def _point_record(point: CalibrationPoint) -> dict[str, Any]:
    return {
        "id": point.identifier,
        "pixel_uv": _pair_record(point.pixel_uv, "u", "v"),
        "machine_xy_mm": _pair_record(point.machine_xy_mm, "x", "y"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
