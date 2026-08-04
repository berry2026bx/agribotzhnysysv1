"""Optional YOLO integration, intentionally isolated from GRBL control."""

from .detector import Detection, DetectorConfig, YoloDetector, select_target

__all__ = ["Detection", "DetectorConfig", "YoloDetector", "select_target"]
