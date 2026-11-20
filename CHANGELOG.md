# Changelog

## Unreleased

- Add MeshZero conflict troubleshooting: disable background operation, stop/disable its service over SSH or CLI, or uninstall it.
- Document the current service-detection limitation and how to restore MeshZero startup.

## 0.1.21 — 2026-11-20

- Publish the APPLaunch/LCD-verified revision to GitHub and the app store; verify global and China registry checksums. Preserve the test device's existing identity, channels, messages and US radio profile.

- Add an opt-in Scotland / ScotMesh preset following the community wiki: UK/EU radio settings, 3-byte path hashes and default flood scope sco.
- Apply firmware-compatible scope transport codes to channel floods and startup/manual flood adverts before transmission; retain existing settings for other regions.
- Document Scotland setup and the current lack of per-channel scope overrides.

## 0.1.20 — 2026-11-20

- Submit the tested revision to the app store and refresh its listing with channel leaving, identity transfer and updater progress.

- Leave a channel with Backspace in Chats, with a Cancel-first confirmation before removing its local messages and radio subscription.
- Keep Public left across restarts and allow rejoining it from Join.
- Add Settings → Identity import/export using MeshCore firmware's 128-character expanded private-key format, including conversion of existing seed identities without changing their public key.
- Mask imported keys, preview the resulting public key before replacement, export only to an owner-readable local file, and retain the previous identity for restoration.
- Restart after identity replacement while preserving the selected data directory, channels, messages and saved repeater credentials.

## 0.1.19 — 2026-11-20

- Separate updater connection, download, checksum, authentication, package validation, dependency retrieval and installation stages.
- Stream package downloads to disk with received/total MiB, percentage when size is known, a progress bar and live elapsed time.
- Show APT's reported installation progress instead of a single static Installing message.
- Record per-stage durations and outcomes in a bounded private local update.log; retain installer diagnostics and total installation time in the privileged installer log.
- Preserve both checksum checks, package identity/version checks and downgrade protection.
- Use private on-disk download and installer caches instead of keeping package copies in the Zero's RAM-backed /tmp.

## 0.1.18 — 2026-11-20

- Ask whether to save a repeater password after entry, with No selected by default.
- Save only after a successful authenticated status request; encrypt credentials locally with a private device-local key and reuse them by repeater public key.
- Allow Backspace on repeater confirmation/status screens to forget the saved password; failed requests do not replace credentials.
- Publish the user-tested startup advert, immediate Tab navigation, message chime fix and repeater status features to the app store.

## 0.1.17 — 2026-11-20 — test build

- Send one flood advert after startup radio/update checks and any update decision are complete.
- Switch pages immediately with Tab, preserving chat and Join drafts.
- Fix silent short message chimes with a longer stereo chime and speaker wake-up lead-in.
- Label repeaters in Nodes and add Request Status confirmation and a masked, unsaved repeater password.
- Display reported battery voltage with a marked single-cell Li-ion charge estimate, uptime, noise floor, last SNR and repeater UTC clock where supported.
- Hold this revision out of the app store for user testing.

## 0.1.16 — 2026-11-19

- Check GitHub's latest stable release once at startup without blocking radio initialization or keyboard input.
- Offer Update / Later when a newer complete release exists, with Update selected by default; reuse the verified download and installation flow.
- Quietly continue offline or if the release check fails; cancel the checker on exit and preserve drafts when dismissing the prompt.

## 0.1.15 — 2026-11-19

- Open the focused top tab with X or Fn+X (Down), as well as Enter, without changing message typing.
- Honor APPLaunch Settings → Screen → DarkTime, including Never, while keeping the radio listening.
- Wake the display on the first keypress without activating a control or sending a message; restore the backlight on normal exit.
- Play a short chime for newly received channel messages and DMs, respecting system volume/mute. Add Settings → Message sound to turn it off.
- Suppress duplicate-packet chimes and collapse rapid notification bursts; stop playback when the app closes.

## 0.1.14 — 2026-11-19

- Add the Slovakia community preset: 869.618 MHz, BW62.5, SF7, CR4/5 and 2-byte path hashes.
- Use the existing conservative European power and airtime policy; keep the selected profile unchanged until the user chooses another one.


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
