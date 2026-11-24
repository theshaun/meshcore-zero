import asyncio
import hashlib
import hmac
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch, AsyncMock
from types import SimpleNamespace
from PIL import Image, features

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor'))
from Crypto.Cipher import AES
from openhop_core import LocalIdentity, CompanionRadio
from openhop_core.protocol.packet_builder import PacketBuilder
from meshcore_zero.store import Store, PUBLIC_KEY, PRESETS, radio_config
from meshcore_zero.ui import UI
from meshcore_zero.radio import Backend, configure_mesh_sync
from meshcore_zero.hardware import Keyboard, Framebuffer
from meshcore_zero.text import units


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

    def test_coding_rate_override_is_regional_and_active_config_is_stable(self):
        self.store.set('coding_rate_US',8)
        self.assertEqual(radio_config(self.store)['coding_rate'],8)
        self.assertEqual(radio_config(self.store,'EU')['coding_rate'],5)
        backend=Backend(self.store)
        self.store.set('coding_rate_US',6)
        self.assertEqual(backend.config['coding_rate'],8)
        self.assertEqual(radio_config(self.store)['coding_rate'],6)
        self.store.set('coding_rate_US',9)
        with self.assertRaises(ValueError): radio_config(self.store)

    def test_settings_cycles_coding_rate_without_changing_region(self):
        async def scenario():
            ui=UI(self.store)
            ui.screen='settings'; ui.selected=1
            for expected in (6,7,8,5):
                await ui.key('enter')
                self.assertEqual(radio_config(self.store)['coding_rate'],expected)
            self.assertEqual(self.store.get('region','US'),'US')
            self.assertEqual(ui.render().size,(320,170))
        asyncio.run(scenario())

    def test_optional_or_repeated_hashtags_join_the_same_channel(self):
        for name in ('testing','#testing','##testing','###TESTING'):
            self.assertEqual(self.store.join(name),'#testing')
        self.assertEqual(len(self.store.chats()),2)

    def test_join_field_prefills_and_keeps_one_hashtag(self):
        async def scenario():
            ui=UI(self.store)
            await ui.key('tab')
            self.assertEqual(ui.draft,'#')
            await ui.key('backspace')
            self.assertEqual(ui.draft,'#')
            for char in '##testing': await ui.key(char)
            self.assertEqual(ui.draft,'#testing')
            await ui.key('enter')
            self.assertEqual(ui.chat['id'],'#testing')
        asyncio.run(scenario())

    def test_cardputer_symbol_layer_and_navigation(self):
        keyboard=Keyboard.__new__(Keyboard)
        keyboard.shift=set()
        for code,char in ((39,'#'),(71,'-'),(70,'_'),(91,'.'),(28,'enter'),(15,'tab'),(103,'up'),(108,'down'),(33,'f'),(45,'x'),(44,'z'),(46,'c')):
            self.assertEqual(keyboard.translate(1,code,1),char)
        keyboard.translate(1,42,1)
        self.assertEqual(keyboard.translate(1,30,1),'A')
        keyboard.translate(1,42,0)
        self.assertEqual(keyboard.translate(1,30,1),'a')

    def test_inbox_letter_navigation_and_fn_arrows_leave_text_entry_unchanged(self):
        async def scenario():
            self.store.join('#testing');self.store.dm('a'*64,'Fixture')
            ui=UI(self.store);keyboard=Keyboard.__new__(Keyboard);keyboard.shift=set()
            for code,expected in ((45,1),(108,2),(45,2),(33,1),(103,0),(33,0)):
                await ui.key(keyboard.translate(1,code,1));self.assertEqual(ui.selected,expected)
            await ui.key('X');self.assertEqual(ui.selected,1)
            await ui.key('F');self.assertEqual(ui.selected,0)
            await ui.key('enter')
            for char in 'fxFX':await ui.key(char)
            self.assertEqual(ui.draft,'fxFX')
            await ui.key('escape');ui.channel_ui.open(next(c for c in self.store.chats() if c['id']=='#testing'))
            await ui.key('x');self.assertEqual(ui.channel_ui.selected,1)
        asyncio.run(scenario())

    def test_interrupted_send_is_not_left_sending(self):
        self.store.add('public','You','pending',status='sending')
        self.store.db.close()
        self.store=Store(self.tmp.name)
        self.assertEqual(self.store.history('public')[0]['status'],'interrupted')

    def test_ui_tab_join_and_open(self):
        async def scenario():
            ui=UI(self.store)
            await ui.key('tab')
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

    def test_idle_chat_stops_redrawing_and_new_message_invalidates(self):
        ui=UI(self.store)
        ui.open_chat(self.store.chats()[0])
        before=ui.render_key()
        ui.render()
        self.assertEqual(before,ui.render_key())
        self.store.add('public','Alice','new message',unread=True)
        self.assertNotEqual(before,ui.render_key())
        ui.render()
        after=ui.render_key()
        ui.render()
        self.assertEqual(after,ui.render_key())

    def test_compact_chat_uses_local_name_for_legacy_history(self):
        self.store.set('name','Zero 💨')
        self.store.add('public','You','Hello',status='sent')
        self.store.add('public','Ari🪐','Seen')
        ui=UI(self.store)
        lines=ui.chat_lines(self.store.history('public'))
        self.assertEqual([''.join(s for s,_ in row) for row in lines],
            ['● Zero 💨: Hello','Ari🪐: Seen'])
        self.store.add('public','Zero 💨','Retry me',status='failed')
        self.assertIn('[failed]',''.join(s for s,_ in ui.chat_lines(self.store.history('public'))[-1]))

    def test_outgoing_history_saves_actual_node_name(self):
        async def scenario():
            self.store.join('#testing')
            notices=[]
            backend=Backend(self.store,notices.append)
            backend.engine=SimpleNamespace(is_running=True,
                prefs=SimpleNamespace(node_name='Zero 💨'),
                send_channel_message=AsyncMock(return_value=True))
            backend.channels={'#testing':1}
            chat=next(c for c in self.store.chats() if c['id']=='#testing')
            await backend.send(chat,'Hello')
            saved=self.store.history('#testing')[0]
            self.assertEqual((saved['sender'],saved['status']),('Zero 💨','sent'))
            self.assertEqual(notices,[])
        asyncio.run(scenario())

    def test_color_emoji_clusters_survive_wrapping_and_clipping(self):
        ui=UI(self.store)
        name='Zero 👩🏽‍💻🇺🇸💨🪐'
        self.assertEqual([p for p,emoji in units(name) if emoji],['👩🏽‍💻','🇺🇸','💨','🪐'])
        rows=ui.text.wrap([(name+': '+('hello '*20),'white')],90,11)
        for row in rows:
            self.assertLessEqual(ui.text.width(''.join(p for p,_ in row),11),90)
        glyph=ui.text.emoji('🪐',12)
        colors=[(r,g,b) for r,g,b,a in glyph.getdata() if a>128]
        self.assertTrue(any(max(rgb)-min(rgb)>50 for rgb in colors))
        if features.check('raqm'):
            ui.text.emoji('👩🏽‍💻',12)
            self.assertLessEqual(ui.text.emoji_font.getlength('👩🏽‍💻'),
                ui.text.emoji_font.getlength('👩')+1)
        clipped=ui.text.fit('👩🏽‍💻🇺🇸💨🪐',28,11)
        self.assertEqual(clipped,'👩🏽‍💻…')


class FramebufferTests(unittest.TestCase):
    def test_shared_mapping_updates_pixels_with_stride_and_viewport(self):
        stride=644
        size=stride*171
        with tempfile.NamedTemporaryFile() as file:
            file.truncate(size)
            def ioctl(fd,request,buffer):
                if request==0x4600:
                    struct.pack_into('7I',buffer,0,320,170,322,171,1,1,16)
                    for position,field in zip((32,44,56),((11,5,0),(5,6,0),(0,5,0))):
                        struct.pack_into('3I',buffer,position,*field)
                elif request==0x4602:
                    struct.pack_into('I',buffer,16+struct.calcsize('L'),size)
                    struct.pack_into('I',buffer,48,stride)
            with patch('meshcore_zero.hardware.fcntl.ioctl',side_effect=ioctl):
                fb=Framebuffer(file.name)
            try:
                fb.write(Image.new('RGB',(320,170),(255,0,0)))
                # Separate descriptor sees the shared pixels, while viewport and
                # row padding remain untouched. Same path drives LCD dirty pages.
                file.seek(stride)
                self.assertEqual(file.read(4),b'\x00\x00\x00\xf8')
                file.seek(stride+642)
                self.assertEqual(file.read(2),b'\x00\x00')
            finally:
                fb.close()


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_testing_reply_wire_packet_reaches_history_and_inbox(self):
        # Build the packet independently of openHop's encoder, using the
        # MeshCore wire format and hashtag key derivation.
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory)
            try:
                store.join('#testing')
                backend=Backend(store)
                backend.engine=CompanionRadio(None,LocalIdentity(),node_name='Zero')
                backend.sync_channels()
                backend.engine.on_channel_message_event(backend.channel_message)
                secret=hashlib.sha256(b'#testing').digest()[:16]
                sender='Zero 💨'
                body=struct.pack('<I',1795044000)+b'\x00'+(sender+': Seen 2').encode('utf-8')
                body+=b'\x00'*(-len(body)%16)
                ciphertext=AES.new(secret,AES.MODE_ECB).encrypt(body)
                payload=hashlib.sha256(secret).digest()[:1]+hmac.digest(secret,ciphertext,'sha256')[:2]+ciphertext
                wire=b'\x15\x00'+payload  # flooded group text, zero-hop path
                ui=UI(store,backend)
                before=ui.render_key()
                await backend.engine.node.dispatcher._process_received_packet(wire,-60,9.0)
                self.assertNotEqual(before,ui.render_key())
                history=store.history('#testing')
                self.assertEqual(len(history),1)
                self.assertEqual((history[0]['sender'],history[0]['text']),(sender,'Seen 2'))
                self.assertEqual(store.chats()[0]['id'],'#testing')
                self.assertEqual(store.chats()[0]['unread'],1)
                self.assertEqual(store.history('public'),[])
                ui.open_chat(store.chats()[0])
                self.assertEqual(ui.render().size,(320,170))
                # Repeated flood copies are retained only once.
                await backend.engine.node.dispatcher._process_received_packet(wire,-62,8.0)
                self.assertEqual(len(store.history('#testing')),1)
            finally:
                store.db.close()

    async def test_radio_sync_readback_rejects_wrong_configuration(self):
        class Chip:
            STANDBY_RC=0; RX_CONTINUOUS=0xffffff
            def setStandby(self,value): pass
            def writeRegister(self,address,data,size): self.data=data
            def readRegister(self,address,size): return self.data
            def request(self,value): self.receiving=True
        chip=Chip()
        configure_mesh_sync(chip)
        self.assertEqual(chip.data,(0x14,0x24))
        self.assertTrue(chip.receiving)
        chip.readRegister=lambda address,size:(0,0)
        with self.assertRaises(RuntimeError): configure_mesh_sync(chip)

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
