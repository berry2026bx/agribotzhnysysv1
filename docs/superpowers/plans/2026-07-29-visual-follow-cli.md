# Visual Follow CLI Implementation Plan

Goal: Add a bounded command that converts the live display-only red-target reading into a human-reviewed XY jog proposal. It remains preview-only by default and executes only under an explicit flag.

Architecture: The existing dashboard at port 8765 remains display-only. A new DayuWriter command reads its JSON snapshot, subtracts a physical-P0 visual baseline, creates one X and one Y relative jog at most, and uses the existing persistent GrblController only for explicit execution.

Global constraints:

- Reject snapshots unless `state=ready`, `mapping_state=available`, and `motion_permission=display_only`.
- Never create a Z command.
- Every XY segment must pass the existing 5 mm and 100 mm/min validation.
- Default behavior must not open a serial port.
- Execution must require both `--execute` and `--physical-preflight`.

## Task 1: Proposal Model

Files: create `communication/dayuwriter/visual_follow.py` and `tests/dayuwriter/test_visual_follow.py`.

1. Write a failing test showing that a target at `(6.9, 0.2)` with baseline `(1.9, 0.2)` creates the exact single command `JogCommand("X", 5.0, 50.0)`.
2. Run `python -m pytest tests/dayuwriter/test_visual_follow.py -q` and confirm failure because the new module is absent.
3. Implement `FollowBaseline`, `LiveTarget`, `FollowProposal`, `parse_live_target`, and `build_follow_proposal`; use the existing `validate_jog` for each nonzero axis.
4. Rerun the focused test and confirm it passes.

## Task 2: Guarded Execution

Files: modify `communication/dayuwriter/visual_follow.py` and `tests/dayuwriter/test_visual_follow.py`.

1. Write a failing test that `execute_follow` opens exactly one controller and calls `jog` in X-then-Y order.
2. Write a failing test that the CLI prints `preview only` without `--execute`, and rejects `--execute` if `--physical-preflight` is absent.
3. Implement `execute_follow` with a single `with GrblController(port)` block and a command-line parser whose `--execute` branch requires the acknowledgement flag.
4. Run the focused tests and confirm they pass.

## Task 3: Documentation And Verification

Files: create `docs/dayuwriter/17-visual-follow-first-operation.md`; modify `docs/dayuwriter/README.md`.

1. Document the preview command with the captured P0 baseline and the execution-only safety check.
2. Run `python -m py_compile communication/dayuwriter/visual_follow.py`.
3. Run the full suite using the project interpreter and `git diff --check`.
4. Commit the module, tests, documentation, and this plan as `feat: add bounded visual follow preview`.
