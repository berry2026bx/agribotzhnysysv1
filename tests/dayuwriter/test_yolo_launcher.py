from pathlib import Path


def test_yolo_start_scripts_default_to_display_only_and_record_stop_pid() -> None:
    root = Path(__file__).resolve().parents[2]
    start = (root / "scripts" / "start_dayuwriter_yolo.ps1").read_text(encoding="utf-8")
    stop = (root / "scripts" / "stop_dayuwriter_yolo.ps1").read_text(encoding="utf-8")
    runbook = (root / "docs" / "dayuwriter" / "33-yolo-display-and-supervised-motion.md").read_text(encoding="utf-8")

    assert "ArmMotion" in start
    assert "USB-SERIAL CH340" in start
    assert "live-yolo-dashboard.pid" in start
    assert "live-yolo-dashboard.pid" in stop
    assert "display-only" in runbook
    assert "--baseline-x 0" in runbook
