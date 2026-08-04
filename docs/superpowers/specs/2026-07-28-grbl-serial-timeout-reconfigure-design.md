# GRBL Serial Timeout Reconfiguration Design

## Problem

During a live GRBL jog on Windows, `GrblController._write_until` set
`serial_port.write_timeout` for every outgoing status query. pySerial documents
that changing this property reconfigures an open serial port. The CH340 path
raised Windows error 31 during that reconfiguration while waiting for jog
completion. The jog's physical completion was therefore unknown.

## Chosen Approach

Keep the serial port's configured write timeout unchanged whenever it already
fits within the remaining controller deadline. Only temporarily lower it when
the deadline is shorter than the configured timeout, then restore it after the
write. This preserves the deadline cap while avoiding redundant Windows COM
reconfiguration in normal `?` polling and jog completion paths.

## Scope

- Modify only `GrblController._write_until`.
- Add a controller test using a serial double that rejects runtime
  `write_timeout` changes after `open()`.
- Verify a normal `status()` query still sends `?` and parses `Idle` without a
  runtime timeout reconfiguration.
- Retain the existing short-deadline test, which must still temporarily lower
  the timeout.

## Non-Goals

- No change to `$J=G91` command generation, feeds, distance caps, bounds,
  GRBL firmware, or physical motion.
- No automatic retry of an interrupted jog.
- No RealSense/dashboard changes in this fix.

## Safety And Verification

The production change is test-first. The new regression test must fail against
the current implementation because it writes the same timeout value at runtime.
After the minimal conditional assignment, the focused controller tests and the
full test suite must pass. Live follow-up remains read-only status confirmation
followed by physical P0 re-establishment before any jog.
