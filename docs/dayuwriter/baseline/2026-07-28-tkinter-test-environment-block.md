# Tkinter Test Environment Block

## Observation

On 2026-07-28, the full pytest command stopped during collection of the
existing `tests/dayuwriter/test_grbl_monitor.py` module:

```text
ImportError: DLL load failed while importing _tkinter:
Application control policy blocked this file.
```

The error occurs while Python imports the standard-library `tkinter` package
from the current `dayuwriter-control` environment.  It occurs before any
monitor test runs and before the new plane-mapping module is imported by that
test, so it is not evidence of a regression in plane mapping.

## Verified Instead

```text
python -m pytest tests/realsense -q ...                 14 passed
python -m pytest <all non-GUI DayuWriter test modules>  86 passed
```

The command-line pixel-to-plane mapping also executed against the current
Camera A input and wrote its display-only artifact successfully.

## Follow-Up

Restore the Windows policy permission for `_tkinter` or use a Python
environment allowed to load it before relying on the Tkinter monitor GUI.
This is separate from serial control and from the display-only calibration
artifact.
