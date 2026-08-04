import pytest

from communication.dayuwriter.workspace import Position, parse_mpos, split_delta, validate_xy_target


def test_parse_mpos() -> None:
    assert parse_mpos("<Idle|MPos:12.500,-3.000,1.000|FS:0,0>") == Position(12.5, -3.0, 1.0)


@pytest.mark.parametrize("target", [(-190, -90), (0, 0), (190, 140)])
def test_workspace_accepts_boundaries(target) -> None:
    assert validate_xy_target(*target) == (float(target[0]), float(target[1]))


@pytest.mark.parametrize("target", [(-190.001, 0), (190.001, 0), (0, -90.001), (0, 140.001)])
def test_workspace_rejects_outside_boundaries(target) -> None:
    with pytest.raises(ValueError):
        validate_xy_target(*target)


def test_split_delta_bounds_every_segment() -> None:
    segments = split_delta(12)
    assert sum(segments) == pytest.approx(12)
    assert all(abs(segment) <= 5 for segment in segments)
    assert split_delta(0) == []
