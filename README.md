# MeshCore for Cardputer Zero

Standalone MeshCore messaging for M5Stack Cardputer Zero with the SX1262 LoRa
CAP. Chat over LoRa without a phone, companion radio, or internet connection.

![Inbox](screenshots/inbox.png)
![Conversation](screenshots/chat.png)

## Requirements

- Cardputer Zero with the SX1262 LoRa CAP and a suitable antenna.
- The Debian 13 / ARM64 image with Python 3.13 and APPLaunch.
- Matching radio settings on the other nodes you want to reach.

This is early-access software. US operation has been tested; EU presets are
included, but EU over-the-air validation is still pending.

## Install

SSH into your Cardputer Zero, then run:

```sh
curl -fL https://github.com/unagisan69/meshcore-zero/releases/latest/download/meshcore-zero_arm64.deb -o /tmp/meshcore-zero.deb
sudo apt install /tmp/meshcore-zero.deb
```

If you prefer `wget`, use it for the download instead:

```sh
wget -O /tmp/meshcore-zero.deb https://github.com/unagisan69/meshcore-zero/releases/latest/download/meshcore-zero_arm64.deb
sudo apt install /tmp/meshcore-zero.deb
```

Open **MeshCore** in APPLaunch. If the icon has not appeared, refresh or restart
the launcher. Application updates preserve your identity, channels, and history.

## Update

In **Settings → Update app**, check GitHub for a newer release, press Enter to
download it, then enter your device’s sudo password to install. The password is
used only for that installation and is never saved or sent to GitHub. Keep power
connected during installation; the app restarts when finished. Updates preserve
your local identity, channels, and messages.

## Using MeshCore

- **Tab** cycles through Chats, Join, Nodes, and Settings; **Enter** opens.
- **Up/Down** selects a conversation or scrolls chat history. Use the keyboard's
  Fn arrow combinations where necessary.
- Type in a conversation and press **Enter** to send.
- **Escape** returns to Chats; Escape again exits to the launcher.
- **Join** opens with `#` already entered. Type the channel name;
  entering another leading `#` is harmless.
- **Nodes** lists discovered nodes. Select a chat node and press Enter to start
  a direct message. Infrastructure nodes remain visible in the list.
- **Settings** controls region, coding rate, node name, announcements, and app updates.

The inbox combines channels and direct messages, with message previews and
unread counts. Names and messages support offline color Unicode emoji.

## Sharing the LoRa CAP with MeshZero

Available in GitHub releases from **v0.1.12**. The pending store candidate stays
at v0.1.11 while the store reviews the permission-file location.

If MeshZero’s background service is running, MeshCore shows a notice with one
**Okay** button. Press Enter to close that service and continue. MeshCore waits
for shutdown before accessing the CAP. It does not delete MeshZero’s data or
disable its startup setting; it can run again when you start it or reboot.
If shutdown fails, the radio stays unopened and an error is shown.

The package grants the radio’s `gpio` group permission to run only
`systemctl stop meshzero.service` without a password. It does not grant general
service-management or root access. Another radio app must not be started while
MeshCore is using the CAP.

## Radio settings and CAPs

Both the current **Cap LoRa-1262** and the legacy **Cap LoRa868** are detected
automatically. Settings shows the detected model. The legacy CAP does not need
the newer board’s antenna-switch expander.

**Settings → Region** offers USA, Europe (legacy), Japan (experimental), Canada,
Australia, New Zealand, EU/UK, Switzerland, Czechia, Netherlands, Portugal,
Thailand, and Vietnam. Restart to apply; saved coding-rate overrides and your
existing US/EU configuration are preserved.

Japan uses 920.800 MHz / SF12 / BW125 / CR4/8 at 13 dBm, with energy-based
listen-before-talk and per-packet airtime limits. Text is limited to 16 UTF-8
bytes including a channel’s sender prefix. This is experimental and does not
establish Japanese equipment certification. Use an appropriately approved setup.

See [radio profiles and CAP compatibility](docs/radio.md) for exact settings,
Japan limitations, hardware detection, and field-test coverage. A hashtag channel
changes its shared key, not the radio frequency.

## Message indicators

Small green circles mean a matching radio echo or DM acknowledgement returned.
Muted grey circles mean no confirmation has returned yet.

A transmitted channel message can be heard by another device without any
response returning. A heard indication appears only when MeshCore receives a
matching copy of the message back over the radio. It does not confirm delivery
to every channel member. No confirmation does not mean the transmission failed.
Direct messages can receive an explicit delivery acknowledgement.

Public and hashtag channels are shared channels: anyone with the same channel
name/key can read them. Channel display names are not authenticated identities.

## Your data

Identity, settings, contacts, channels, and messages stay in
`~/.local/share/meshcore-zero/` (or the directory selected by `XDG_DATA_HOME`).
Back up that directory to retain your identity and history. It contains private
key material, so keep backups private. Unsent drafts are currently kept only
while the app is running.

## Help and releases

- [Download releases](https://github.com/unagisan69/meshcore-zero/releases)
- [Report an issue](https://github.com/unagisan69/meshcore-zero/issues)
- [Changelog](CHANGELOG.md)

The app currently focuses on text chat. Attachments, room-server login, GPS,
and a custom frequency editor are not included.

Independent client using [openHop Core](https://github.com/openhop-dev/openhop_core)
and the [MeshCore protocol](https://github.com/meshcore-dev/meshcore).
See [LICENSE](LICENSE) and [third-party notices](THIRD_PARTY_NOTICES.md).
