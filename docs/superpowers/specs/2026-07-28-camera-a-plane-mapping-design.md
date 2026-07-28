# Camera A Plane Mapping Design

## Goal

Convert an RGB pixel `(u, v)` into a predicted DayuWriter `(X, Y)` coordinate
for the fixed D435i A mount, while reporting measured error and never sending
a GRBL command.

## Inputs

A JSON file identifies the camera serial and separates reference observations
into `fit_points` and `validation_points`.  Each observation has a unique ID,
a manually selected pen-tip pixel, and a known machine XY position in mm.

## Mapping

The tool fits a projective 2D homography from image pixels to the paper plane.
At least four non-collinear fit points are required.  Validation points are
not used to fit the mapping.  The output reports each validation residual plus
mean and maximum error in mm.

## Safety Boundary

The module has no serial-port dependency and has no GRBL import.  Its artifact
is explicitly `display_only`; a successful fit is not permission to command
the machine.  Any camera movement, manual machine movement, reset, or new
camera serial invalidates the artifact.

## Error Handling

The tool rejects fewer than four fit points, non-finite coordinates, duplicate
point IDs, rank-deficient point arrangements, invalid homogeneous denominators,
and camera records without a serial number.

## Verification

Synthetic projective correspondences verify exact recovery and held-out
prediction.  Failure tests cover insufficient and degenerate observations.
The current Camera A artifact must report its held-out error, not merely a
zero training residual.
