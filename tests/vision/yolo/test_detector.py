import numpy as np
import pytest

from vision.yolo.detector import DetectorConfig, Detection, parse_result, select_target


class Boxes:
    xyxy = np.array([[10, 20, 50, 80], [float("nan"), 0, 1, 1], [2, 2, 2, 5]])
    conf = np.array([0.9, 0.99, 0.95])
    cls = np.array([1, 0, 1])


class Result:
    boxes = Boxes()
    names = {0: "bottle", 1: "cup"}


def test_parse_result_filters_invalid_and_sorts() -> None:
    detections = parse_result(Result(), 100, 100, DetectorConfig("model.pt", confidence=0.5))
    assert detections == (Detection(1, "cup", 0.9, (10.0, 20.0, 50.0, 80.0)),)


def test_parse_result_filters_requested_classes() -> None:
    config = DetectorConfig("model.pt", confidence=0.5, classes=frozenset({"cup"}))
    detections = parse_result(Result(), 100, 100, config)
    assert len(detections) == 1 and detections[0].class_name == "cup"


def test_select_target_uses_confidence_then_area() -> None:
    detections = (Detection(1, "cup", 0.8, (0, 0, 20, 20)), Detection(1, "cup", 0.9, (0, 0, 1, 1)))
    assert select_target(detections, "cup") == detections[1]
    assert select_target(detections, "bottle") is None


def test_config_rejects_invalid_confidence() -> None:
    with pytest.raises(ValueError, match="confidence"):
        DetectorConfig("model.pt", confidence=2)


def test_detector_converts_realsense_rgb_to_bgr_for_numpy_model_input() -> None:
    class Model:
        def __init__(self) -> None:
            self.source = None

        def predict(self, *, source, **_kwargs):
            self.source = source
            return []

    model = Model()
    detector = __import__("vision.yolo.detector", fromlist=["YoloDetector"]).YoloDetector(
        DetectorConfig("model.pt"), model=model
    )

    assert detector.predict(np.array([[[1, 2, 3]]], dtype=np.uint8)) == ()
    assert model.source.tolist() == [[[3, 2, 1]]]
