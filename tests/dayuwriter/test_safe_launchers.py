from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_one_click_launcher_starts_only_display_and_monitor_components() -> None:
    launcher = (PROJECT_ROOT / "scripts" / "start_dayuwriter_session.ps1").read_text(
        encoding="utf-8"
    )

    assert "run_dayuwriter_dashboard.ps1" in launcher
    assert "run_dayuwriter_grbl_monitor.ps1" in launcher
    assert "visual_follow" not in launcher
    assert "--execute" not in launcher


def test_vscode_task_uses_the_safe_one_click_launcher() -> None:
    tasks = (PROJECT_ROOT / ".vscode" / "tasks.json").read_text(encoding="utf-8")

    assert "DayuWriter: Safe start dashboard and monitor" in tasks
    assert "start_dayuwriter_session.ps1" in tasks
    assert "visual_follow" not in tasks
    assert "--execute" not in tasks
