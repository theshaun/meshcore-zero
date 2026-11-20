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

### App store — recommended

Open **Store** on your Cardputer Zero, search for **MeshCore** or enter share
code **MCZR**, then install it. Open **MeshCore** from APPLaunch afterward.

[View MeshCore in the Cardputer app store](https://cardputer.cc/#/apps/MCZR)

The store listing shows the available version. **v0.1.13** adds a MeshZero
background-service warning. Close MeshZero’s background service before opening
MeshCore so the two apps do not share the CAP. See the
[troubleshooting options](#troubleshooting-meshcore-freezes-or-cannot-use-the-lora-cap)
below.

### GitHub release — manual alternative

To install directly from GitHub instead, SSH into your Cardputer Zero and run:

```sh
mkdir -p "$HOME/.cache/meshcore-zero"
curl -fL https://github.com/unagisan69/meshcore-zero/releases/latest/download/meshcore-zero_arm64.deb -o "$HOME/.cache/meshcore-zero/meshcore-zero.deb"
sudo apt install "$HOME/.cache/meshcore-zero/meshcore-zero.deb"
```

If you prefer `wget`, use it for the download instead:

```sh
mkdir -p "$HOME/.cache/meshcore-zero"
wget -O "$HOME/.cache/meshcore-zero/meshcore-zero.deb" https://github.com/unagisan69/meshcore-zero/releases/latest/download/meshcore-zero_arm64.deb
sudo apt install "$HOME/.cache/meshcore-zero/meshcore-zero.deb"
```

Open **MeshCore** in APPLaunch. If the icon has not appeared, refresh or restart
the launcher. Application updates preserve your identity, channels, and history.

## Update

At startup, MeshCore checks GitHub for a newer stable release when the device has internet access. If one is available, **Update** is selected by default; press **Enter** to continue, or choose **Later** / press **Esc**. Offline checks are skipped quietly and do not block radio startup.

In **Settings → Update app**, check GitHub for a newer release, press Enter to
download it, then enter your device’s sudo password to install. The password is
used only for that installation and is never saved or sent to GitHub. Keep power
connected during installation; the app restarts when finished. Updates preserve
your local identity, channels, and messages. This checks GitHub releases and may
install a version newer than the app-store version.

The update screen separates downloading, verification and installation. It shows
received/total MiB and a percentage when the server provides a size, elapsed
time, and the package manager's installation progress. An activity bar is used
when a stage has no measurable percentage.
These indicators are available after installing v0.1.19; older versions use
their existing update screen for that first installation.

The in-app updater uses private on-disk caches for package downloads and staging
to reduce RAM use. Temporary package copies are removed when the operation ends.

If an update is slow, its stage timings and outcomes are recorded locally in
`~/.local/share/meshcore-zero/update.log` (under your selected data directory if
overridden). The log rotates after 256 KiB and keeps one previous copy. It
contains timing fields, not passwords or messages. For installer errors, inspect
`sudo tail -n 80 /var/log/meshcore-zero-update.log` over SSH.

## Using MeshCore

- **Tab** cycles through Chats, Join, Nodes, and Settings and immediately displays each page. **Enter** acts on the visible page.
- **Up/Down** selects a conversation or scrolls chat history. Use the keyboard's
  Fn arrow combinations where necessary.
- Type in a conversation and press **Enter** to send.
- **Escape** returns to Chats; Escape again exits to the launcher.
- **Join** opens with `#` already entered. Type the channel name;
  entering another leading `#` is harmless.
- In **Chats**, highlight a channel and press **Backspace** for **Channel options**: mute/unmute notifications, Scope, clear history, or leave. Confirm **Leave** to remove that channel and its saved messages from this device; **Cancel** is selected by default. Muted channels keep receiving messages and unread counts, without chimes or notification toasts. Clearing history keeps the channel joined. Direct messages are unaffected. To rejoin Public, open **Join**, press **Down** to select **Join / open Public channel**, then **Enter**.
- **Nodes** lists discovered nodes. Select a chat node and press Enter to start
  a direct message. Repeaters and room servers remain visible in the list.
- Select a **Repeater** and press **Enter**, then confirm **Request Status** and enter its password. The password is masked. After entry, choose whether to save it (**No** is selected by default). A successful status request saves it encrypted on this device if you choose **Yes**; future requests reuse it for that repeater. Press **Backspace** on the repeater confirmation or status screen to forget it. Status shows battery voltage and an approximate single-cell Li-ion percentage, uptime, noise floor, last SNR and the repeater's UTC clock. Unsupported clock queries show **Unavailable**; other battery types may not have a meaningful percentage.
- After startup checks and any update decision, MeshCore sends one flood advert to introduce your node. You can also use **Settings → Announce this node**.
- **Settings** controls region, coding rate, node name, announcements, message sound, identity import/export, encrypted backup/restore, and app updates.
- The display follows the system **Settings → Screen → DarkTime** timeout, including **Never**. The first keypress wakes the screen without activating anything. Messages continue arriving while the screen is dark.
- New channel messages and DMs play a short chime at the system volume. System mute silences it; **Settings → Message sound** switches it off for MeshCore. Receiving a message does not wake the screen.

The inbox combines channels and direct messages, with message previews and
unread counts. Names and messages support offline color Unicode emoji.

## Troubleshooting: MeshCore freezes or cannot use the LoRa CAP

If **MeshZero** is installed, its background radio can keep the LoRa CAP busy
after its window closes. This can interfere with MeshCore and other apps that
need the same hardware. You do **not** have to uninstall MeshZero to use MeshCore;
choose one of these options:

1. **Disable background operation in MeshZero:** open MeshZero, go to **Setup**,
   scroll to **Run in background**, and switch it **Off**. Close MeshZero and
   allow time for its radio to be released before opening MeshCore.

2. **Stop the service through SSH or the Cardputer CLI:** run:

   ```sh
   sudo systemctl stop meshzero.service
   ```

   This stops it now without uninstalling MeshZero. To also prevent it from
   starting automatically at the next boot, use:

   ```sh
   sudo systemctl disable --now meshzero.service
   ```

   To restore automatic startup later:

   ```sh
   sudo systemctl enable --now meshzero.service
   ```

   Exit MeshCore before restarting MeshZero's radio service.

3. **Uninstall MeshZero if you no longer want it:** remove it through the
   Cardputer app store, or run:

   ```sh
   sudo apt remove meshzero
   ```

   Back up any MeshZero identity/configuration you want to retain before
   uninstalling. This command removes MeshZero, not MeshCore.

**Current warning limitation (v0.1.13–v0.1.14):** MeshCore checks whether
`meshzero.service` is active, rather than whether its radio is actually in use.
The service can remain active after background operation is turned off, so
MeshCore's warning may persist even after MeshZero releases the CAP. If that
happens, use the service-stop command or uninstall option above.

From v0.1.13, the warning keeps MeshCore's radio unopened. After stopping the
service, press **Okay** to check again, or **Esc** to exit. MeshCore does not stop
other services automatically. Do not start another radio app while MeshCore is
using the CAP.

If these steps do not resolve a freeze, report your MeshCore version, OS image,
CAP revision, and error log. This conflict is one possible cause, not a diagnosis
of every freeze. Never post your identity database or private keys in an issue.

## Radio settings and CAPs

Both the current **Cap LoRa-1262** and the legacy **Cap LoRa868** are detected
automatically. Settings shows the detected model. The legacy CAP does not need
the newer board’s antenna-switch expander.

**Settings → Region** offers USA, Europe (legacy), Japan (experimental), Canada,
Australia, New Zealand, EU/UK, Switzerland, Czechia, Netherlands, Portugal,
Thailand, Vietnam, Slovakia, and Scotland (ScotMesh). Restart to apply; saved coding-rate overrides and your
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

The **Scotland · ScotMesh** preset uses the UK/EU radio settings (869.618 MHz,
BW62.5, SF8, CR4/8), 3-byte path hashes, and default flood scope **sco**.
Restart to apply it. The default scope covers channel floods and startup/manual
flood adverts; joining a channel does not select a separate scope. In **Chats → Backspace →
Scope**, enter an override such as `edi`, `gla`, `ioi`, `wls` or `eng-ne`.
Clear the field to inherit the regional default. The effective scope appears in
the chat header. An override affects future outgoing channel floods, including
Public; it does not filter incoming messages or change adverts/other channels.
See the [ScotMesh setup guide](https://wiki.scotmesh.uk/en/MeshCore/getting-started).

## Identity import and export

Open **Settings → Identity: import / export** to move an identity between MeshCore
firmware and this app. This uses the firmware's **64-byte expanded private key
(128 hexadecimal characters)**. Existing app identities are converted on export
without changing their public key. A 64-character public key or seed is not a
firmware private-key export and cannot be pasted here.

- **Import firmware key** accepts the 128-character key with masked entry.
- **Import from file** reads a plain-text key file. The default is
  `~/.local/share/meshcore-zero/identity-import.txt`; you can edit the path.
- Import previews the resulting **public key**, with **Cancel** selected by
  default. Confirming restarts the app with the new identity and keeps your
  channels, messages and saved repeater passwords. **Restore previous identity**
  lets you switch back to the last identity replaced through this menu.
- **Export firmware key** asks for confirmation, then writes
  `~/.local/share/meshcore-zero/identity-export.txt` with owner-only file access.
  It does not show the private key on screen. Exporting again replaces this file.

Paths follow your selected data directory if overridden. Keep key files and
backups private, and remove transfer files when finished. Avoid operating two
active devices with the same identity at once.

## Encrypted backup and restore

Open **Settings → Backup / restore**. **Create encrypted backup** asks for a
password twice (8–128 characters) and writes a private `.mczb` file under
`~/.local/share/meshcore-zero/backups/`. It includes your identity, previous
identity backup, settings, channels and scopes/mute choices, DMs, all saved
messages, discovered nodes and saved repeater passwords. Copy the file off the
device with your preferred SSH/SFTP tool. Keep the password separately: the app
does not save it and cannot recover a forgotten password.

**Restore encrypted backup** lists local backup files, or accepts another file
path. Copy a backup onto the device first. Enter its password to validate it and
preview its public identity and conversation counts. **Cancel** is selected by
default. Restoring replaces the entire local dataset, including radio settings;
it does not merge histories. Before replacement, an encrypted `before-restore-…`
recovery backup is saved with the same password you just entered. The radio stops,
data is replaced transactionally, and the app restarts with a result screen.
Use the recovery file through the same menu to undo a successful restore.

Backup encryption uses Argon2id password derivation and XSalsa20-Poly1305
(SecretBox) authentication. Wrong passwords and damaged or unsupported files are
rejected before any local data is replaced. Files are owner-readable only.
The current backup safety limit is 16 MiB of unencrypted data; larger datasets
require the manual directory backup below. `.mczb` is MeshCore Zero's full-backup
format, separate from the firmware-compatible identity import/export above.
Avoid using the same restored identity on two active devices simultaneously.

## Your data

Identity, settings, contacts, channels, and messages stay in
`~/.local/share/meshcore-zero/` (or the directory selected by `XDG_DATA_HOME`).
Back up that directory to retain your identity and history. It contains private
key material, so keep backups private. Unsent drafts are currently kept only
while the app is running.

Optional saved repeater passwords are encrypted with a device-local key in that
same directory. Back up the whole directory to retain both the passwords and
their key. They are not uploaded to GitHub or included in app packages.

## Help and releases

- [Download releases](https://github.com/unagisan69/meshcore-zero/releases)
- [Report an issue](https://github.com/unagisan69/meshcore-zero/issues)
- [Changelog](CHANGELOG.md)

The app currently focuses on text chat. Attachments, room-server login, GPS,
and a custom frequency editor are not included.

Independent client using [openHop Core](https://github.com/openhop-dev/openhop_core)
and the [MeshCore protocol](https://github.com/meshcore-dev/meshcore).
See [LICENSE](LICENSE) and [third-party notices](THIRD_PARTY_NOTICES.md).
