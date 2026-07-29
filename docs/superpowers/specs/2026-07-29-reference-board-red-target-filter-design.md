# Reference-Board Red Target Filter

## Problem

The live camera can see red objects outside the printed A4 sheet. The current
detector chooses the largest valid red connected component, so a paper-external
red region can replace the intended red square and produce an invalid
machine-plane coordinate.

## Decision

When the ArUco reference tracker is `ready`, the dashboard will accept only
red candidates whose RGB pixel centre maps inside the registered A4 paper
rectangle. Candidate selection remains in the display-only process; the
dashboard continues to have no serial or GRBL access.

## Boundaries

- A candidate outside the A4 plane is ignored, even if it is larger.
- If every candidate is outside, the dashboard reports `no_target`.
- The existing bounded visual-follow command independently rejects non-ready,
out-of-range, or unconfirmed motion; this filter does not authorize motion.
- This fixes the observed alternating target at `(248,44)` versus the paper
target near `(686,504)`. It does not claim sub-millimetre placement accuracy.
