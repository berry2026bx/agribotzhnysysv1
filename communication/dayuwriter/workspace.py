from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite


X_MIN_MM = -190.0
X_MAX_MM = 190.0
Y_MIN_MM = -90.0
Y_MAX_MM = 140.0
MAX_SEGMENT_MM = 5.0


@dataclass(frozen=True)
class Position:
    x: float
    y: float
    z: float


def parse_mpos(status_raw: str) -> Position:
    fields = status_raw.strip("<>").split("|")
    mpos = next((field[5:] for field in fields if field.startswith("MPos:")), None)
    if mpos is None:
        raise ValueError(f"status has no MPos field: {status_raw!r}")
    values = mpos.split(",")
    if len(values) != 3:
        raise ValueError(f"invalid MPos field: {mpos!r}")
    try:
        position = Position(*(float(value) for value in values))
    except ValueError as exc:
        raise ValueError(f"invalid MPos field: {mpos!r}") from exc
    if not all(isfinite(value) for value in (position.x, position.y, position.z)):
        raise ValueError(f"non-finite MPos field: {mpos!r}")
    return position


def validate_xy_target(x: float, y: float) -> tuple[float, float]:
    x = float(x)
    y = float(y)
    if not isfinite(x) or not isfinite(y):
        raise ValueError("XY target must be finite")
    if not X_MIN_MM <= x <= X_MAX_MM:
        raise ValueError(f"X target must be within [{X_MIN_MM:g}, {X_MAX_MM:g}] mm")
    if not Y_MIN_MM <= y <= Y_MAX_MM:
        raise ValueError(f"Y target must be within [{Y_MIN_MM:g}, {Y_MAX_MM:g}] mm")
    return x, y


def split_delta(delta_mm: float) -> list[float]:
    delta = float(delta_mm)
    if not isfinite(delta):
        raise ValueError("movement delta must be finite")
    if delta == 0:
        return []
    count = ceil(abs(delta) / MAX_SEGMENT_MM)
    segment = delta / count
    return [segment] * count
