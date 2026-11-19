"""CAP hardware lifecycle and in-process MeshCore protocol engine.

openHop calls its high-level engine CompanionRadio, but it runs HERE on the
Zero. No serial/BLE companion, TCP server, or second device is involved.
"""
import asyncio
import fcntl
import json
import logging
import os
from pathlib import Path
import time
from collections import OrderedDict

from .store import radio_config

log = logging.getLogger(__name__)


def configure_mesh_sync(chip):
    # The vendored wrapper accepts sync_word but does not program it. Set and
    # read back the SX1262 private-network sync bytes used by MeshCore.
    chip.setStandby(chip.STANDBY_RC)
    chip.writeRegister(0x0740, (0x14, 0x24), 2)
    if tuple(chip.readRegister(0x0740, 2)) != (0x14, 0x24):
        raise RuntimeError('SX1262 sync word readback failed')
    chip.request(chip.RX_CONTINUOUS)


class CapPower:
    def __init__(self):
        self.saved = []
        self.i2c = None

    def start(self):
        from periphery import I2C
        try:
            for name in ('ext_5v_out', 'grove_5v_out'):
                path = Path('/sys/class/leds') / name / 'brightness'
                value = path.read_text().strip()
                self.saved.append((path, value))
                if value == '0':
                    path.write_text('1')
            time.sleep(.15)
            self.i2c = I2C('/dev/i2c-1')
            self.registers = {reg: self.read(reg) for reg in (3, 5, 7)}
            self.write(3, self.registers[3] | 1)  # P0 output
            self.write(7, self.registers[7] & ~1)  # P0 drive enabled
            self.write(5, self.registers[5] | 1)  # RF antenna switch
            if not self.read(5) & 1:
                raise RuntimeError('CAP antenna switch readback failed')
        except Exception:
            self.close()
            raise

    def read(self, reg):
        from periphery import I2C
        messages = [I2C.Message([reg]), I2C.Message([0], read=True)]
        self.i2c.transfer(0x43, messages)
        return messages[1].data[0]

    def write(self, reg, value):
        from periphery import I2C
        self.i2c.transfer(0x43, [I2C.Message([reg, value])])

    def close(self):
        if self.i2c:
            for reg, value in getattr(self, 'registers', {}).items():
                try:
                    # Restore only P0, preserving other CAP pins.
                    self.write(reg, (self.read(reg) & ~1) | (value & 1))
                except Exception:
                    log.exception('Restoring CAP register')
            self.i2c.close()
            self.i2c = None
        for path, value in reversed(self.saved):
            try:
                path.write_text(value)
            except Exception:
                log.exception('Restoring CAP power')
        self.saved.clear()


class Backend:
    def __init__(self, store, notify=lambda text: None):
        self.store, self.notify = store, notify
        self.engine = self.radio = None
        self.power = CapPower()
        self.state = 'Starting radio'
        self.error = ''
        self.channels = {}
        self.lock = None
        self.send_lock = asyncio.Lock()
        self.next_tx = 0
        self.region = store.get('region', 'US')
        self.config = radio_config(store, self.region)
        self._outgoing_mid = None
        self._outgoing_started = 0
        self._early_echoes = OrderedDict()

    async def start(self):
        from openhop_core import CompanionRadio, LocalIdentity
        from openhop_core.hardware.sx1262_wrapper import SX1262Radio
        try:
            self.lock = open('/tmp/meshcore-zero-radio.lock', 'w')
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.power.start()
            region = self.store.get('region', 'US')
            self.region = region
            cfg = radio_config(self.store, region)
            self.config = cfg
            self.radio = SX1262Radio(bus_id=0, cs_id=1, cs_pin=-1,
                gpio_chip=0, use_gpiod_backend=True, reset_pin=26,
                busy_pin=22, irq_pin=23, txen_pin=-1,
                preamble_length=16, sync_word=0x12,
                use_dio2_rf=True, use_dio3_tcxo=True, dio3_tcxo_voltage=3.0, **cfg)
            if not self.radio.begin():
                raise RuntimeError('SX1262 initialization failed; check CAP seating')
            configure_mesh_sync(self.radio.lora)
            seed = self.store.get('identity')
            if seed is None:
                identity = LocalIdentity()
                seed = identity.signing_key.encode().hex()
                self.store.set('identity', seed)
            identity = LocalIdentity(bytes.fromhex(seed))
            self.engine = CompanionRadio(self.radio, identity,
                node_name=self.store.get('name', 'Zero-' + identity.get_public_key().hex()[:4]),
                radio_config=cfg)
            self.engine.contacts.load_from_dicts([json.loads(r[0]) for r in self.store.db.execute('SELECT data FROM nodes')])
            self.engine.set_autoadd_config(0x0f)
            self.sync_channels()
            self.engine.on_channel_message_event(self.channel_message)
            self.engine.on_message_event(self.direct_message)
            self.engine.on_advert_received(self.advert)
            self.watch_echoes()
            await self.engine.start()
            self.state = region + ' · Radio ready'
            log.info('Radio active: %.3f MHz, %.1f kHz, SF%d, CR4/%d, %d dBm',
                cfg['frequency']/1e6, cfg['bandwidth']/1e3,
                cfg['spreading_factor'], cfg['coding_rate'], cfg['tx_power'])
        except Exception as exc:
            log.exception('Radio startup')
            self.error = str(exc)
            await self.close()
            self.state = 'Radio offline'
            self.notify(self.error)

    def sync_channels(self):
        if self.engine:
            for idx, row in enumerate(self.store.db.execute("SELECT * FROM chats WHERE kind='channel' ORDER BY rowid")):
                self.engine.set_channel(idx, row['name'], bytes.fromhex(row['secret']))
                self.channels[row['id']] = idx

    def watch_echoes(self):
        dispatcher=self.engine.node.dispatcher
        previous=dispatcher.packet_sent_callback
        async def sent(packet):
            if previous:
                await previous(packet)
            self.packet_sent(packet)
        dispatcher.set_packet_sent_callback(sent)
        # This hook precedes MeshCore's duplicate suppression. Echoed packets
        # are deliberately suppressed by the normal receive path.
        dispatcher.add_raw_rx_subscriber(self.radio_received)

    def packet_sent(self, packet):
        if self._outgoing_mid is None or packet.get_payload_type() != 5:
            return
        packet_hash=packet.calculate_packet_hash().hex()
        self.store.bind_tx(self._outgoing_mid,packet_hash)
        early=self._early_echoes.pop(packet_hash,None)
        if early and early[1] >= self._outgoing_started:
            self.store.heard(packet_hash,early[0])

    def radio_received(self, data, rssi=0, snr=0):
        from openhop_core.protocol import Packet
        packet=Packet()
        try:
            packet.read_from(data)
            if packet.get_payload_type()!=5 or packet.get_route_type() not in (0,1):
                return
            hops=packet.get_path_hash_count()
        except (ValueError,IndexError,TypeError):
            return
        # Full payload hash excludes the mutable route, so it matches only
        # the original encrypted datagram even when a relay has appended hops.
        packet_hash=packet.calculate_packet_hash().hex()
        if self.store.heard(packet_hash,hops):
            log.info('Heard rebroadcast %s via %d hop(s)',packet_hash[:12],hops)
        else:
            self._early_echoes[packet_hash]=(hops,time.monotonic())
            self._early_echoes.move_to_end(packet_hash)
            while len(self._early_echoes)>256:
                self._early_echoes.popitem(last=False)

    def persist_contacts(self):
        if self.engine:
            with self.store.db:
                for row in self.engine.contacts.to_dicts():
                    self.store.db.execute('INSERT OR REPLACE INTO nodes VALUES(?,?)', (row['public_key'], json.dumps(row)))

    async def advert(self, data):
        self.persist_contacts()

    async def channel_message(self, event):
        chat = next((k for k, v in self.channels.items() if v == event.channel_idx), None)
        if chat:
            sender, separator, body = event.text.partition(': ')
            self.store.add(chat, sender if separator else event.sender_name, body if separator else event.text, event.timestamp,
                token=event.packet_hash, unread=True)
            self.notify('New message · ' + event.channel_name)
        self.engine.sync_next_message()  # history has durably accepted the event

    async def direct_message(self, event):
        key = event.sender_key.hex()
        contact = self.engine.get_contact_by_key(event.sender_key)
        name = contact.name if contact else key[:8]
        self.store.dm(key, name)
        self.store.add(key, name, event.text, event.timestamp, token=event.packet_hash, unread=True)
        self.notify('New message · ' + name)
        self.engine.sync_next_message()

    async def send(self, chat, text):
        if not self.engine or not self.engine.is_running:
            raise ValueError('Radio offline · message not sent')
        # Firmware payload limit includes the sender prefix in channel messages.
        overhead = len((self.engine.prefs.node_name + ': ').encode()) if chat['kind'] == 'channel' else 0
        if not text.strip() or len(text.encode()) + overhead > 150:
            raise ValueError('Message too long (150 bytes including name)')
        async with self.send_lock:
            if time.monotonic() < self.next_tx:
                raise ValueError('Airtime cooldown · try again shortly')
            mid = self.store.add(chat['id'], self.engine.prefs.node_name, text, status='sending')
            self._outgoing_mid=mid if chat['kind']=='channel' else None
            self._outgoing_started=time.monotonic()
            try:
                if chat['kind'] == 'channel':
                    ok = await self.engine.send_channel_message(self.channels[chat['id']], text)
                    state = 'sent' if ok else 'failed'
                else:
                    result = await self.engine.send_text_message(bytes.fromhex(chat['id']), text, wait_for_ack=True)
                    state = 'delivered' if result.success else 'unconfirmed'
                self.store.status(mid, state)
                # Conservative per-transmission 1% airtime pacing in EU, 10% US.
                from openhop_core.protocol.packet_utils import calculate_lora_airtime_ms
                cfg = self.config
                airtime = calculate_lora_airtime_ms(200, cfg['spreading_factor'], cfg['bandwidth'], cfg['coding_rate'], 16)
                self.next_tx = time.monotonic() + airtime / 1000 * (99 if self.region == 'EU' else 9)
                if state not in ('sent','delivered'):
                    self.notify(state.capitalize())
            except BaseException:
                self.store.status(mid, 'failed')
                raise
            finally:
                self._outgoing_mid=None

    async def announce(self):
        if not self.engine:
            raise ValueError('Radio offline')
        async with self.send_lock:
            if time.monotonic() < self.next_tx:
                raise ValueError('Airtime cooldown · try again shortly')
            ok = await self.engine.advertise(flood=True)
            self.next_tx = time.monotonic() + (60 if self.region == 'EU' else 6)
            self.notify('Announcement sent' if ok else 'Announcement failed')

    async def close(self):
        if self.engine:
            self.persist_contacts()
            await self.engine.stop()
            self.engine = None
        if self.radio:
            self.radio.cleanup()
            self.radio = None
        self.power.close()
        if self.lock:
            self.lock.close()
            self.lock = None
