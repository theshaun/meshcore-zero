The native protocol engine in `vendor/openhop_core` is openHop Core (MIT),
vendored without modification from commit
`e07722ea96093752ac8b3c6772d653f8b68224bf`:
https://github.com/openhop-dev/openhop_core
The license is retained in `vendor/OPENHOP_LICENSE`. Its bundled LoRaRF driver
retains its upstream notices. Runtime wheels retain their license metadata in
the package's `runtime` directory.

Protocol references: https://github.com/meshcore-dev/meshcore and
https://github.com/meshcore-dev/meshcore-cli. These repositories are reference
material and are not copied into this application.

CAP wiring and antenna-switch register semantics were checked against
https://github.com/CardputerZero/Cap-LoRa-1262 and M5Stack's documentation.
No source code from that application is included.

This is an independent client, not an official meshcore-dev application.
