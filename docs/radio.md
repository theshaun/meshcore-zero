# Radio profiles and CAP compatibility

Select **Settings → Region**, choose a profile with Up/Down, then press Enter.
Restart MeshCore to apply it. Selecting or cancelling a profile never transmits.
Existing US/EU profiles and per-profile coding-rate overrides are preserved.

| Profile | MHz | BW kHz | SF | CR | TX dBm | Path hash bytes |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| US | 910.525 | 62.5 | 7 | 4/5 | 20 | 1 |
| EU (legacy) | 869.618 | 62.5 | 8 | 4/5 | 14 | 1 |
| Japan (experimental) | 920.800 | 125 | 12 | 4/8 | 13 | 1 |
| Canada | 910.525 | 62.5 | 7 | 4/5 | 20 | 3 |
| Australia (narrow) | 916.575 | 62.5 | 7 | 4/7 | 20 | 2 |
| New Zealand (narrow) | 917.375 | 62.5 | 7 | 4/5 | 20 | 2 |
| EU / UK | 869.618 | 62.5 | 8 | 4/8 | 14 | 1 |
| Switzerland | 869.618 | 62.5 | 8 | 4/8 | 14 | 1 |
| Czechia | 869.432 | 62.5 | 7 | 4/5 | 14 | 2 |
| Netherlands | 869.618 | 62.5 | 7 | 4/5 | 14 | 1 |
| Portugal (868) | 869.618 | 62.5 | 7 | 4/6 | 14 | 1 |
| Thailand | 921.000 | 62.5 | 7 | 4/5 | 13 | 1 |
| Vietnam (narrow) | 920.250 | 62.5 | 8 | 4/5 | 13 | 1 |
| Scotland / ScotMesh | 869.618 | 62.5 | 8 | 4/8 | 14 | 3 |
| Slovakia | 869.618 | 62.5 | 7 | 4/5 | 14 | 2 |

These are offline community starting points, not universal national settings or
an equipment approval. Match your local mesh's radio settings and antenna band.
The values (except legacy EU and experimental Japan) follow the
[official MeshCore preset API](https://api.meshcore.nz/api/v1/config), checked
2026-11-18. Power defaults are conservative application choices; the API does not
specify them. The app deliberately excludes 433 MHz and presets outside the
CAP's published 868–923 MHz range. US peer messaging has been tested; other
profiles need local field testing. No automatic frequency changes or online
preset downloads take place.

## Scotland / ScotMesh

The separate Scotland preset follows the [ScotMesh setup guide](https://wiki.scotmesh.uk/en/MeshCore/getting-started)
and [scope guidance](https://wiki.scotmesh.uk/en/MeshCore/scopes), checked 2026-11-20:
UK/EU radio settings, default scope `sco` and 3-byte path hashes. The public
transport key is derived from `#sco` using MeshCore's SHA-256 convention; it is
routing scope, not an extra encryption password. Channel floods and flood
adverts use this default. Direct routes retain their routing mode. Other
presets remain unscoped and keep their existing path-hash defaults.

Select Scotland explicitly and restart; installing this update does not switch
your region or join channels. Join `#scotland` yourself for the community chat.
Channels inherit `sco` unless a scope override is saved in Chats → Backspace →
Scope. A blank scope field restores inheritance. Overrides affect only that
channel's outgoing floods, including Public, and never change the node's default
or advert scope. Scottish on-air forwarding still needs local field
validation; tests verify serialized scope codes and 3-byte path encoding offline.

## Japan (experimental)

The 920.800 MHz / SF12 / BW125 / CR4/8 setting follows the
[MeshCore Japan community proposal](https://github.com/meshcore-dev/MeshCore/issues/2079).
It is not currently in the official preset API.

The physical TX path applies these controls to messages, retries, acknowledgements,
and announcements:

- TX power at most 13 dBm, on the selected 920.800 MHz / BW125 profile.
- Repeated RSSI energy samples over at least 5 ms, below −80 dBm, before TX.
- Busy, missing, or invalid sensing cancels TX; it is never forced after timeout.
- Packets with estimated airtime of 4 seconds or more are refused.
- At least 50 ms between completion of a send attempt and the next TX.

The composer limits text to 16 UTF-8 bytes (including the sender prefix for a
channel message). Use a short node name; Japanese characters occupy multiple
bytes. A routed packet can still exceed the airtime cap and be refused. Long
announcements may also exceed it. Failed sends remain visible in history.

These are software controls on a general-purpose Linux host, not a calibrated
RF conformance test or a Giteki approval. Japan operation requires an appropriately
certified hardware/antenna/software combination. The profile has not been tested
on air in Japan. See [ARIB STD-T108](https://www.arib.or.jp/english/html/overview/doc/5-STD-T108v1_5-E1.pdf)
for the relevant equipment classes and conditions.

## Automatic CAP detection

Both boards use the SX1262 on SPI0 CE1 with the same radio GPIO wiring:

| Board | Detection and antenna control |
| --- | --- |
| Current Cap LoRa-1262 | Recognize the PI4IOE5V6408 at I²C address 0x43; enable its P0 antenna switch and verify readback. |
| Legacy Cap LoRa868 | Allow the absent expander, then require an SX126x silicon signature over SPI. No expander writes. |

An unrelated I²C device, permission error, or failed antenna-switch write is not
silently treated as an older CAP. Floating SPI bus responses cannot pass detection.
Power and switch state are restored at exit, preserving other expander pins.
Settings shows the detected model after radio startup.

Hardware facts were cross-checked with [M5Stack's CAP documentation](https://docs.m5stack.com/en/cap/Cap_LoRa-1262),
the [PI4IOE5V6408 datasheet](https://www.diodes.com/part/view/PI4IOE5V6408), and
[MeshZero's hardware detection](https://github.com/s0liton/MeshZero/blob/22ec6f98a4283c7b7e4d66bec030a1956839881a/src/daemon/hw.cpp).
The detection implementation is independent; no MeshZero application code is bundled.
Automated tests cover both revisions, missing boards, and failed detection.
Only the available physical CAP has been tested; legacy hardware field validation
remains pending. Power the device off before changing CAPs.

The Japan profile caps transmitted text at 16 UTF-8 bytes (including the sender
prefix on channels), and rejects any serialized packet whose predicted airtime
reaches 4 seconds. This can reject long routed DMs and node advertisements at
SF12. Shorter coding rates may allow more RF capacity, but the text cap stays
conservative. Busy or unavailable RSSI sensing cancels transmission rather than
forcing it; every physical packet is checked, including automatic replies.
RSSI is sampled over at least 5 ms at a -80 dBm threshold and transmissions are
spaced at least 50 ms apart. These are host-software safeguards, not a measured
or certified implementation of [ARIB STD-T108](https://www.arib.or.jp/english/html/overview/doc/5-STD-T108v1_5-E1.pdf).
Use equipment and firmware/configuration approved for your installation.

## CAP detection

| CAP | Detection | Antenna enable |
| --- | --- | --- |
| Current Cap LoRa-1262 | PI4IOE5V6408 ID at I²C 0x43, then SX126x SPI signature | P0 high; preserve other pins |
| Legacy Cap LoRa868 | No expander acknowledgement, then SX126x SPI signature | No external expander needed |

Missing or floating SPI cannot be accepted as an attached CAP. Permission errors,
unrecognized expander IDs, and antenna-switch write failures remain errors rather
than silently becoming a legacy CAP. Power and the switch pin are restored on
exit; identity and history are unaffected. Power off before swapping CAPs.

Hardware facts were cross-checked against [M5Stack's board documentation](https://docs.m5stack.com/en/cap/Cap_LoRa-1262)
and [MeshZero's detection logic](https://github.com/s0liton/MeshZero/blob/22ec6f98a4283c7b7e4d66bec030a1956839881a/src/daemon/hw.cpp).
This is an independent Python implementation; MeshZero's GPL source is not
included. Unit tests cover both detection paths and failure modes. A real
legacy CAP still needs a separate hardware validation run.

## Slovakia

The **Slovakia (SK)** profile follows the community’s
[current radio settings](https://mesh.om3kff.sk/) and
[2-byte path-hash recommendation](https://mesh.om3kff.sk/settings.html):
869.618 MHz, BW62.5, SF7, CR4/5, and 2-byte path hashes. Checked 2026-11-19.
The profile uses this app’s conservative 14 dBm European power default and
a 10% rolling-hour airtime budget. The community frequency page does not specify TX power.
Select it in Settings → Region and restart to apply. Existing identities,
channels, radio profiles and per-region coding-rate overrides are preserved.
This configures the radio and path width; it does not join community channels
or change their flood scopes. Slovakia over-the-air testing remains pending.

## Burst-friendly airtime accounting

v0.1.26 removes per-message and per-announcement cooldowns. European presets
use a shared 360-second rolling-hour budget for their 869.4–869.65 MHz band.
The ledger counts calculated airtime of actual encoded physical packets,
including protocol ACKs/retries, just before SetTx. Failed/uncertain TX attempts
remain charged conservatively. Entries expire one hour after the reserved
packet end. Restarting, switching presets, or restoring an identity backup
does not clear the separate local airtime.sqlite ledger. Clock rollback fails
closed until the clock catches up; a clock correction forward follows the
system clock. This tracks this app’s transmissions only, not other radio apps.

The 10% UK band alternative is documented in [Ofcom IR 2030,
IR2030/1/19](https://www.ofcom.org.uk/siteassets/resources/documents/spectrum/interface-requirements/ir-2030.pdf),
checked 2026-11-21. These host-side guards are not equipment certification.
Power defaults remain unchanged. Japan’s existing physical guards are retained.

## Manual region scope and path size

Settings → Scope / path hash overrides the selected profile’s default flood
scope and outgoing path hash size (1, 2 or 3 bytes). Values are stored per
profile and applied before the startup advert on the next launch. Empty scope
is an explicit unscoped override, including on the Scotland preset; Reset to
region preset deletes both overrides and restores defaults such as sco / 3B.
Per-channel scope overrides take precedence for channel messages only.
Pending changes do not relabel the running radio’s scope in channel menus or
chat headers. Full encrypted backup/restore preserves and validates overrides.

The firmware [packet format](https://github.com/meshcore-dev/MeshCore/blob/main/docs/packet_format.md)
supports 1-, 2- and 3-byte paths; 4 bytes is reserved. The path size setting
controls this node’s outgoing encoding, not which hash sizes repeaters forward.
No regional RF defaults or joined-channel secrets change when editing these
protocol settings. Scope/path wire-format tests run without transmitting.
