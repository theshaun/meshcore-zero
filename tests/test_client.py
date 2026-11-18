import asyncio
import hashlib
import hmac
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor'))
from Crypto.Cipher import AES
from openhop_core import LocalIdentity, CompanionRadio
from openhop_core.protocol.packet_builder import PacketBuilder
from meshcore_zero.store import Store, PUBLIC_KEY, PRESETS
from meshcore_zero.ui import UI
from meshcore_zero.radio import Backend


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(self.tmp.name)

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def test_channel_and_history_survive_restart(self):
        cid=self.store.join(' #Asheville ')
        self.assertEqual(cid,'#asheville')
        self.assertEqual(self.store.chats()[1]['secret'],hashlib.sha256(b'#asheville').digest()[:16].hex())
        self.store.add(cid,'Alice','hello',token='packet1',unread=True)
        self.store.add(cid,'Alice','hello',token='packet1',unread=True)
        self.assertEqual(self.store.chats()[0]['unread'],1)
        self.assertEqual(len(self.store.history(cid)),1)
        self.store.db.close()
        self.store=Store(self.tmp.name)
        self.assertEqual(self.store.chats()[0]['preview'],'hello')
        self.store.read(cid)
        self.assertEqual(self.store.chats()[0]['unread'],0)

    def test_invalid_channel_names(self):
        for value in ('', '#', 'with spaces', 'a'*31, '#hello/there'):
            with self.assertRaises(ValueError): self.store.join(value)

    def test_interrupted_send_is_not_left_sending(self):
        self.store.add('public','You','pending',status='sending')
        self.store.db.close()
        self.store=Store(self.tmp.name)
        self.assertEqual(self.store.history('public')[0]['status'],'interrupted')

    def test_ui_tab_join_and_open(self):
        async def scenario():
            ui=UI(self.store)
            await ui.key('tab'); await ui.key('tab'); await ui.key('enter')
            self.assertEqual(ui.screen,'join')
            for char in 'meshcore': await ui.key(char)
            await ui.key('enter')
            self.assertEqual(ui.chat['name'],'#meshcore')
            for char in 'draft': await ui.key(char)
            await ui.key('escape')
            ui.open_chat(next(c for c in self.store.chats() if c['id']=='#meshcore'))
            self.assertEqual(ui.draft,'draft')
            self.assertEqual(ui.render().size,(320,170))
        asyncio.run(scenario())

    def test_offline_send_does_not_record_success(self):
        async def scenario():
            backend=Backend(self.store)
            with self.assertRaises(ValueError):
                await backend.send(self.store.chats()[0],'hello')
            self.assertEqual(self.store.history('public'),[])
        asyncio.run(scenario())


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_group_payload_matches_firmware_crypto(self):
        # Independent wire decoder: timestamp LE, plain flags, zero padding,
        # AES-128 ECB and the first 2 bytes of HMAC-SHA256 with the raw PSK.
        key=bytes.fromhex(PUBLIC_KEY)
        pkt=PacketBuilder.create_group_datagram('Public',LocalIdentity(), 'Hello mesh', 'Zero',
            [{'name':'Public','secret':PUBLIC_KEY}], timestamp=1700000000)
        payload=pkt.get_payload()
        self.assertEqual(payload[0],hashlib.sha256(key).digest()[0])
        self.assertEqual(payload[1:3],hmac.digest(key,payload[3:],'sha256')[:2])
        plain=AES.new(key,AES.MODE_ECB).decrypt(payload[3:])
        self.assertEqual(struct.unpack('<I',plain[:4])[0],1700000000)
        self.assertEqual(plain[4],0)
        self.assertEqual(plain[5:].rstrip(b'\0'),b'Zero: Hello mesh')

    async def test_two_nodes_advert_channel_dm_and_ack(self):
        class Radio:
            def __init__(self): self.peer=None; self.callback=None
            def set_rx_callback(self,cb): self.callback=cb
            async def send(self,data):
                if self.peer.callback:
                    asyncio.get_running_loop().call_soon(self.peer.callback,bytes(data),-70,8.0)
                return {'airtime_ms':10}
            async def start_rx(self): pass
            async def stop_rx(self): pass
            def get_last_rssi(self): return -70
            def get_last_snr(self): return 8.0
        a,b=Radio(),Radio(); a.peer=b; b.peer=a
        alice=CompanionRadio(a,LocalIdentity(),node_name='Alice')
        bob=CompanionRadio(b,LocalIdentity(),node_name='Bob')
        received=[]; groups=[]
        for node in (alice,bob):
            node.set_autoadd_config(15)
            node.set_channel(0,'Public',bytes.fromhex(PUBLIC_KEY))
        bob.on_message_event(lambda event:received.append(event.text))
        bob.on_channel_message_event(lambda event:groups.append(event.text))
        await alice.start(); await bob.start()
        try:
            self.assertTrue(await alice.advertise())
            self.assertTrue(await bob.advertise())
            await asyncio.sleep(.2)
            self.assertEqual(alice.get_contact_count(),1)
            self.assertEqual(bob.get_contact_count(),1)
            self.assertTrue(await alice.send_channel_message(0,'hello channel'))
            await asyncio.sleep(.2)
            self.assertEqual(groups,['Alice: hello channel'])
            result=await alice.send_text_message(bob.get_public_key(),'hello privately',wait_for_ack=True)
            self.assertTrue(result.success)
            await asyncio.sleep(.2)
            self.assertEqual(received,['hello privately'])
        finally:
            await alice.stop(); await bob.stop()


if __name__=='__main__': unittest.main()
