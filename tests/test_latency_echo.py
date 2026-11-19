import asyncio
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from PIL import Image, ImageChops

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor'))
from openhop_core import CompanionRadio, LocalIdentity
from openhop_core.protocol import Packet
from openhop_core.protocol.packet_builder import PacketBuilder
from meshcore_zero.store import Store
from meshcore_zero.radio import Backend
from meshcore_zero.ui import UI
from meshcore_zero.hardware import Framebuffer


class DirtyFramebufferTests(unittest.TestCase):
    def test_one_pixel_change_preserves_other_pixels_and_identical_frame_is_skipped(self):
        size=320*170*2
        with tempfile.NamedTemporaryFile() as file:
            file.truncate(size)
            def ioctl(fd,request,buffer):
                if request==0x4600:
                    struct.pack_into('7I',buffer,0,320,170,320,170,0,0,16)
                    for pos,field in zip((32,44,56),((11,5,0),(5,6,0),(0,5,0))):
                        struct.pack_into('3I',buffer,pos,*field)
                else:
                    struct.pack_into('I',buffer,16+struct.calcsize('L'),size)
                    struct.pack_into('I',buffer,48,640)
            with patch('meshcore_zero.hardware.fcntl.ioctl',side_effect=ioctl):
                fb=Framebuffer(file.name)
            try:
                frame=Image.new('RGB',(320,170))
                fb.write(frame)
                file.seek(0);file.write(b'\x12\x34');file.flush()
                frame.putpixel((100,140),(255,0,0));fb.write(frame)
                file.seek(0);self.assertEqual(file.read(2),b'\x12\x34')
                offset=(140*320+100)*2
                file.seek(offset);self.assertEqual(file.read(2),b'\x00\xf8')
                file.seek(offset);file.write(b'\x56\x78');file.flush()
                fb.write(frame)
                file.seek(offset);self.assertEqual(file.read(2),b'\x56\x78')
            finally:
                fb.close()


class ComposerTests(unittest.TestCase):
    def test_typing_repaints_only_the_composer_and_new_messages_invalidate_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory)
            store.add('public','Alice 🪐','Hello')
            ui=UI(store);ui.open_chat(store.chats()[0])
            with patch.object(ui,'chat_lines',wraps=ui.chat_lines) as history_layout:
                first=ui.render()
                for draft in ('h','he','hello 💨'):
                    ui.draft=draft
                    frame=ui.render()
                    bounds=ImageChops.difference(first,frame).getbbox()
                    self.assertGreaterEqual(bounds[1],129)
                    self.assertLessEqual(bounds[3],153)
                self.assertEqual(history_layout.call_count,1)
                store.add('public','Alice','New message',unread=True)
                ui.render()
                self.assertEqual(history_layout.call_count,2)
                ui.notice('New message')
                frame=ui.render()
                # Notifications no longer cover the typing field.
                self.assertEqual(frame.crop((5,130,315,152)).tobytes(),
                    ui._chat_cache.crop((5,130,315,152)).tobytes())
            store.db.close()


class EchoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(self.tmp.name);self.store.join('#testing')
        self.backend=Backend(self.store)
        self.identity=LocalIdentity()
        self.engine=CompanionRadio(None,self.identity,node_name='Zero')
        self.backend.engine=self.engine
        self.backend.sync_channels();self.backend.watch_echoes()

    async def asyncTearDown(self):
        self.store.db.close();self.tmp.cleanup()

    def packet(self,text='Echo test',timestamp=1795050000):
        return PacketBuilder.create_group_datagram('#testing',self.identity,text,'Zero',
            self.engine.channels.get_channels(),timestamp=timestamp)

    @staticmethod
    def echoed(packet,path=b'\xab',path_len=1):
        copy=Packet();copy.read_from(packet.write_to())
        copy.path_len=path_len;copy.path=bytearray(path)
        return copy.write_to()

    async def test_echo_is_seen_before_dedupe_and_survives_restart(self):
        packet=self.packet()
        mid=self.store.add('#testing','Zero','Echo test',status='sent')
        self.backend._outgoing_mid=mid
        self.backend._outgoing_started=time.monotonic()
        await self.engine.node.dispatcher.packet_sent_callback(packet)
        self.engine.node.dispatcher.packet_filter.track_packet(packet.calculate_packet_hash().hex()[:16])
        # Two-byte path hashes encode their width in the high path_len bits.
        wire=self.echoed(packet,b'\xab\xcd',0x41)
        await self.engine.node.dispatcher._process_received_packet(wire,-70,8)
        row=self.store.history('#testing')[0]
        self.assertIsNotNone(row['heard_at']);self.assertEqual(row['heard_hops'],1)
        self.assertEqual(len(self.store.history('#testing')),1)
        changes=self.store.db.total_changes
        await self.engine.node.dispatcher._process_received_packet(wire,-71,7)
        self.assertEqual(self.store.db.total_changes,changes)
        ui=UI(self.store)
        self.assertTrue(''.join(p for p,_ in ui.chat_lines([row])[0]).startswith('● '))
        self.store.db.close();self.store=Store(self.tmp.name)
        self.assertEqual(self.store.history('#testing')[0]['heard_at'],row['heard_at'])

    async def test_early_echo_race_zero_hop_unrelated_and_failed_sends(self):
        packet=self.packet()
        mid=self.store.add('#testing','Zero','Echo test',status='sending')
        self.backend._outgoing_mid=mid
        self.backend._outgoing_started=time.monotonic()
        self.backend.radio_received(packet.write_to())  # A matching zero-hop packet received over RF is also evidence.
        self.backend.radio_received(self.echoed(self.packet('Other packet')))
        self.backend.radio_received(b'')
        await self.engine.node.dispatcher.packet_sent_callback(packet)
        self.assertIsNotNone(self.store.history('#testing')[0]['heard_at'])
        # A returned packet can beat the TX-completion callback.
        self.backend.radio_received(self.echoed(packet))
        self.assertIsNotNone(self.store.history('#testing')[0]['heard_at'])
        self.store.status(mid,'failed')
        self.backend.radio_received(self.echoed(packet))
        self.assertIsNone(self.store.history('#testing')[0]['heard_at'])
        next_packet=self.packet('Next packet',1795050001)
        second=self.store.add('#testing','Zero','Next packet',status='sending')
        self.backend._outgoing_mid=second
        self.backend._outgoing_started=time.monotonic()
        self.backend.radio_received(self.echoed(next_packet))
        await self.engine.node.dispatcher.packet_sent_callback(next_packet)
        self.assertIsNotNone(self.store.history('#testing')[-1]['heard_at'])
        stale=self.packet('Stale',1795050002)
        self.backend.radio_received(self.echoed(stale))
        await asyncio.sleep(.001)
        self.backend._outgoing_started=time.monotonic()
        third=self.store.add('#testing','Zero','Stale',status='sending')
        self.backend._outgoing_mid=third
        await self.engine.node.dispatcher.packet_sent_callback(stale)
        self.assertIsNone(self.store.history('#testing')[-1]['heard_at'])

    async def test_full_send_tracks_an_echo_that_beats_tx_completion(self):
        class EchoRadio:
            def set_rx_callback(inner,callback): inner.callback=callback
            async def send(inner,data):
                packet=Packet();packet.read_from(data)
                asyncio.get_running_loop().call_soon(inner.callback,self.echoed(packet),-70,8)
                await asyncio.sleep(.01)
                return {'airtime_ms':10}
        self.engine=CompanionRadio(EchoRadio(),self.identity,node_name='Zero')
        self.backend.engine=self.engine
        self.backend.sync_channels();self.backend.watch_echoes()
        await self.engine.start()
        try:
            chat=next(c for c in self.store.chats() if c['id']=='#testing')
            await self.backend.send(chat,'Complete send')
            row=self.store.history('#testing')[0]
            self.assertEqual(row['status'],'sent')
            self.assertIsNotNone(row['tx_hash']);self.assertIsNotNone(row['heard_at'])
            self.assertIsNone(self.backend._outgoing_mid)
        finally:
            await self.engine.stop()


class MigrationTests(unittest.TestCase):
    def test_legacy_history_is_preserved_when_adding_echo_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            db=sqlite3.connect(Path(directory)/'meshcore.sqlite')
            db.executescript("""CREATE TABLE messages(id INTEGER PRIMARY KEY,chat TEXT,
                sender TEXT,text TEXT,timestamp INTEGER,status TEXT,token TEXT UNIQUE);
                INSERT INTO messages VALUES(1,'public','You','Legacy message',123,'sent',NULL);""")
            db.commit();db.close()
            store=Store(directory)
            row=store.history('public')[0]
            self.assertEqual(row['text'],'Legacy message')
            self.assertIsNone(row['heard_at']);self.assertIsNone(row['tx_hash'])
            store.db.close()


if __name__=='__main__': unittest.main()
