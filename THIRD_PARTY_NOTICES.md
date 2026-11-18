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

`assets/fonts/NotoColorEmoji.ttf` is Noto Color Emoji, redistributed under
SIL Open Font License 1.1; its license is `assets/fonts/OFL.txt`.
Source: https://github.com/googlefonts/noto-emoji/tree/main/2D/fonts
Bundled font SHA-256: `15671215ab769fdc7162a045d56fd7d7e477c51b04e6b3c761d914d8fdd6cc44`.
The font displays Unicode emoji with Noto artwork, including emoji entered
in iMessage; it does not bundle Apple's proprietary emoji artwork.

`assets/fonts/emoji-sequences.json` is generated from Unicode Emoji 18.0
`emoji-test.txt` (2026-04-30) at
https://unicode.org/Public/emoji/latest/emoji-test.txt.
Redistribution terms are retained in `assets/fonts/UNICODE_LICENSE.txt`.
