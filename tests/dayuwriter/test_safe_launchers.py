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


def test_vscode_task_opens_the_corrected_desktop_gui_not_the_legacy_auto_follow() -> None:
    tasks = (PROJECT_ROOT / ".vscode" / "tasks.json").read_text(encoding="utf-8")

    assert "DayuWriter: Open simple desktop launcher" in tasks
    assert "start_dayuwriter_gui.ps1" in tasks
    assert "DayuWriter: Arm automatic visual follow from P0" not in tasks
    assert "start_dayuwriter_auto_follow.ps1" not in tasks


def test_legacy_auto_follow_script_refuses_to_reintroduce_dynamic_p0() -> None:
    launcher = (PROJECT_ROOT / "scripts" / "start_dayuwriter_auto_follow.ps1").read_text(
        encoding="utf-8"
    )

    assert "retired" in launcher
    assert "start_dayuwriter_gui.cmd" in launcher
    assert "run_dayuwriter_continuous_follow.ps1" not in launcher
