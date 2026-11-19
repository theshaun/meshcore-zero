# Changelog

## 0.1.13 — 2026-11-19

- Store-compatible MeshZero background-service warning, with the SSH stop command, Okay to recheck and Esc to exit.
- Keep the CAP unopened while MeshZero is active or its state cannot be checked.
- Remove automatic service stopping and its rejected sudoers permission file.

## Documentation updates

- Recommend the approved Cardputer app-store installation first, with share code MCZR and a direct listing link.
- Clarify the available store version and newer GitHub-only MeshZero handoff feature.

## 0.1.12 — 2026-11-19

- Released on GitHub; the store candidate remains v0.1.11 pending approval of the exact-unit stop permission’s install location.
- Check MeshZero’s system service before initializing the CAP.
- Show a single Okay notice when MeshZero is running; stop its service and verify shutdown before opening the radio.
- Keep startup responsive during service checks and prevent radio initialization if the handoff fails.
- Package a narrowly scoped permission for radio users to stop only meshzero.service, without a password prompt.


## 0.1.11 — 2026-11-18

- Compact, centered Chats / Join / Nodes / Settings tabs with the current section highlighted.
- Show a fuel-gauge battery icon at the top right, without percentage text.
- Poll battery state away from keyboard handling to keep typing responsive.
- Remove the grey/no-echo legend from the chat footer.


## 0.1.10 — 2026-11-18

- Scrollable regional radio picker with experimental Japan and additional community presets.
- Preserve existing US/EU settings and per-region coding-rate overrides.
- Configure community path-hash widths for Canada, Australia, New Zealand and Czechia.
- Japan: 13 dBm, RSSI-based clear-channel checks, 4-second airtime cap and 50 ms TX spacing, including automatic packets.
- Detect current CAP antenna-switch hardware and legacy CAPs without an I²C expander; verify the SPI radio signature.
- Document hardware coverage and regional limitations.


## 0.1.9 — 2026-11-18

- Muted dark grey unconfirmed-message dots so green confirmations stand out.
- Updated app store listing for the first public store submission.


## 0.1.8 — 2026-11-18

- Small green/red message indicators; recognize matching zero-hop radio echoes.
- Settings updater downloads and verifies GitHub releases and preserves local data.
- Public installation instructions using curl or wget directly on the device.
- Remove device-specific details from documentation, fixtures, build paths, and history.


## 0.1.7 — 2026-11-18

- Faster typing through vectorized pixel conversion, partial screen updates,
  cached composition, and keyboard-triggered redraws.
- Outgoing message indicators for transmission, matching returned broadcasts,
  and acknowledged direct messages.
- Persistent confirmation metadata and backward-compatible database migration.
- Keep notifications clear of the draft field.

## 0.1.6 — 2026-11-18

- Cache glyph measurements and message layout for responsive long conversations.

## 0.1.5 — 2026-11-18

- Compact inbox and inline `Name: message` chat layout.
- Display the local node name on outgoing messages.
- Offline color emoji with support for joined sequences, flags, and skin tones.
- Remove redundant channel markers and successful-send labels.

## 0.1.4 — 2026-11-18

- Configurable coding rate, saved separately for each radio profile.
- Apply active coding-rate settings to transmit cooldown calculations.

## 0.1.3 — 2026-11-18

- Updated app icon.
- Prefilled hashtag entry and normalized duplicate leading hashtags.

## 0.1.2 — 2026-11-18

- Reliable LCD refresh through shared framebuffer mapping.
- Avoid unnecessary redraws while idle.

## 0.1.1 — 2026-11-18

- Correct native keyboard symbol mapping and radio sync-word programming.

## 0.1.0 — 2026-11-18

- Initial standalone Cardputer Zero/SX1262 client.
- Combined channels and direct messages, saved history, node discovery, and
  US/EU radio profiles.
