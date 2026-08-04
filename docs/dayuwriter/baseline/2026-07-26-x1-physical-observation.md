# First X Jog Physical Observation

- Command sent: `$J=G91 X1 F50`
- GRBL response: `ok`
- Reported in-motion status: `Jog`, `MPos X=0.888`
- Physical observation: no axis moved and no motor sound was heard.

This separates protocol acceptance/open-loop position reporting from confirmed mechanical motion. No Y/Z jog is authorized until the motor power and driver path are checked.
