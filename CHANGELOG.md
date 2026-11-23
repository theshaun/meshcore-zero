# Changelog

## 0.1.28 — 2026-11-23

- Add Settings → Scope / path hash with per-profile region scope, explicit unscoped mode, 1/2/3-byte outgoing path hashes and reset to preset (issue #7). Apply before startup adverts after restarting.
- Preserve per-channel overrides, show the active radio’s scope while saved changes await restart, and include validated overrides in encrypted backups.
- Document settings controls, defaults, scope inheritance and firmware path-size compatibility.

## 0.1.27 — 2026-11-21

- Publish to GitHub and the Cardputer app store (submission #629); verify both live registry versions and package SHA-256 checksums. Pass 126 local/ARM64 and GitHub CI tests; install/open through APPLaunch and preserve existing identity, channels and history.

- Release the driver’s transmit-buffer ownership before restoring receive mode after a rejected or failed send, including hourly budget exhaustion. Add a regression test ensuring SetTx is skipped and RX delivery remains enabled.

## 0.1.26 — 2026-11-21

- Remove fixed message, advert and repeater-request cooldowns (issue #5).
- Allow burst conversations within a persistent 10% rolling-hour European airtime budget, calculated from actual physical packet lengths and including ACKs/retries. Preserve Japan’s physical radio guards.
- Keep the airtime ledger separate from identity backups; retain reception when the transmit budget is exhausted.
- Pass 125 local/ARM64 tests, install through APPLaunch, and send three short #testing messages without a cooldown; verify identity, channels and existing history remain intact.

## Documentation updates — 2026-11-20

- Clarify that current MeshZero defaults background operation off and releases the radio about ten seconds after exit; uninstalling is not normally required.
- Explain MeshCore's service-state detection can still produce a false warning after hardware release, and distinguish a temporary service stop from optional startup changes.

## 0.1.25 — 2026-11-20

- Publish the physically confirmed correction to GitHub and the app store; verify both store registries against the tested package checksum.

- Give Public a compact vector globe in Chats and its chat header, distinct from hashtag channels (#), private channels (lock) and direct messages (@).

## 0.1.24 — 2026-11-20

- Publish the APPLaunch/LCD-verified release to GitHub and the app store; verify global and China registry package checksums.

- Replace Join with a channel-type selector for Hashtag, Private and Public, showing only the required fields and defaulting to Hashtag on every visit.
- Accept firmware-compatible 16-byte private channel keys as 32 hex characters or Base64; mask key entry and clear it when leaving the form.
- Reject zero/Public keys, name-derived keys, ambiguous names and duplicate channel-key subscriptions. Preserve existing history when reopening an already-joined private key.
- Distinguish public/hashtag channels with a # marker, private channels with a compact vector lock, and DMs with @ in Chats; mark private chat headers too.
- Include private channels in encrypted full backups and validate them on restore; keep older public/hashtag-only backups compatible.
- Verify private group encryption/decryption against independent firmware-format packets without transmitting private-channel test traffic.

## 0.1.23 — 2026-11-20

- Publish the tested map/GPS revision to the Cardputer app store; verify the global and China listings against the tested package checksum.

- Add a compact Map tab with north-up offline radar, two distance rings, coloured node markers, zoom/auto-fit, selection and node details.
- Read CAP GPS at 115200 baud without receiver commands; validate NMEA checksums/fixes, restore UART settings at exit, and avoid active GPS daemons or serial consoles.
- Use fresh GPS locally, label a recent lost fix, and support a manually saved fallback position; never infer distance from signal strength or plot missing coordinates.
- Mark older node positions, retain verified-advert receive times and last-leg RSSI/SNR, and keep all location-free nodes in Nodes.
- Add opt-in GPS broadcasting in Settings, off by default with Cancel-first confirmation. Include fresh fixes in adverts, send at most every 15 minutes automatically, and respect regional airtime cooldowns.
- Never broadcast the manual fallback; recheck sharing/fix availability immediately before actual location-advert transmission and cancel queued adverts when disabled.
- Keep five centred tabs and the battery icon within the existing header. Document map controls and location-sharing privacy.

## 0.1.22 — 2026-11-20

- Open channel options with Backspace in Chats: mute/unmute notifications, set an optional scope override, clear history or leave, with Cancel-first destructive confirmations.
- Keep muted-channel messages and unread counts while suppressing their chime and toast.
- Apply scope overrides to individual channel packets without changing the node default, other channels or adverts; display the effective scope in chat.
- Add Settings → Backup / restore for password-encrypted, authenticated backups of identity, settings, conversations, messages, nodes and saved repeater passwords.
- Validate backups before confirmation, save an encrypted pre-restore recovery copy, stop the radio before replacing data transactionally, and restart with a visible result.
- Keep secrets masked, use private local files and exclude backup files from Git. Backup files are not firmware identity exports.

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
