import asyncio
import base64
import copy
import hashlib
import hmac
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor'))
from Crypto.Cipher import AES
from meshcore_zero.channels import join_private,parse_key,channel_type,PUBLIC_KEY
from meshcore_zero.store import Store
from meshcore_zero.ui import UI
from meshcore_zero.radio import Backend
from meshcore_zero import backup
from openhop_core import CompanionRadio,LocalIdentity
SEED=bytes(range(32));KEY=bytes(range(1,17)) # Disposable fixture, not a real channel.

class PrivateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);self.addCleanup(self.store.db.close);self.ui=UI(self.store)
    def test_key_formats_validation_names_and_deduplication(self):
        for text in (KEY.hex(),KEY.hex().upper(),base64.b64encode(KEY).decode(),base64.b64encode(KEY).decode().rstrip('=')):
            self.assertEqual(parse_key(text),KEY)
        for text in ('password','00'*16,PUBLIC_KEY,'11'*32,base64.b64encode(bytes(32)).decode()):
            with self.assertRaises(ValueError):parse_key(text)
        cid=join_private(self.store,'Family 🪐',KEY.hex());self.assertEqual(channel_type(self.store.chats()[-1]),'private')
        self.assertEqual(join_private(self.store,'Different local label',base64.b64encode(KEY).decode()),cid)
        with self.store.db:self.store.db.execute('UPDATE chats SET secret=? WHERE id=?',(KEY.hex().upper(),cid))
        self.assertEqual(join_private(self.store,'Same imported key',KEY.hex()),cid)
        self.store.add(cid,'Fixture','Keep history');self.assertEqual(len(self.store.history(cid)),1)
        for name in ('','Public','#family','x'*33,'bad\x00name'):
            with self.assertRaises(ValueError):join_private(self.store,name,bytes(range(2,18)).hex())
        with self.assertRaises(ValueError):join_private(self.store,'Family 🪐',bytes(range(2,18)).hex())
        with self.assertRaises(ValueError):join_private(self.store,'Family',hashlib.sha256(b'#family').digest()[:16].hex())
        self.store.join('#testing')
        with self.assertRaises(ValueError):join_private(self.store,'Renamed',hashlib.sha256(b'#testing').digest()[:16].hex())

    async def test_join_form_masks_secret_clears_it_on_leave_and_draws_private_marker(self):
        u=self.ui;await u.key('tab');await u.key('right');self.assertEqual(u.join_ui.type,1)
        await u.key('down')
        for c in 'Family':await u.key(c)
        await u.key('enter')
        for c in KEY.hex():await u.key(c)
        with patch.object(u.text,'draw',wraps=u.text.draw) as draw:u.render()
        self.assertNotIn(KEY.hex(),str(draw.call_args_list));self.assertNotIn(KEY.hex(),str(u.render_key()))
        await u.key('enter');await u.key('enter');self.assertEqual(u.screen,'chat');self.assertEqual(u.join_ui.secret,'')
        self.assertEqual(channel_type(u.chat),'private');u.render();await u.key('escape');frame=u.render()
        self.assertEqual(frame.size,(320,170));self.assertEqual(len(self.store.chats()),2)
        await u.key('tab');u.join_ui.field=2
        for c in KEY.hex():await u.key(c)
        await u.key('tab');self.assertEqual(u.join_ui.secret,'')

    async def test_independent_firmware_packet_reaches_private_history_wrong_key_is_rejected(self):
        cid=join_private(self.store,'Family',KEY.hex());backend=Backend(self.store)
        backend.engine=CompanionRadio(None,LocalIdentity(SEED),node_name='Zero');backend.sync_channels()
        backend.engine.on_channel_message_event(backend.channel_message)
        def wire(key,timestamp):
            plain=struct.pack('<I',timestamp)+b'\x00Peer: private fixture'
            plain+=b'\x00'*(-len(plain)%16)
            cipher=AES.new(key,AES.MODE_ECB).encrypt(plain)
            return b'\x15\x00'+hashlib.sha256(KEY).digest()[:1]+hmac.digest(key,cipher,'sha256')[:2]+cipher
        await backend.engine.node.dispatcher._process_received_packet(wire(bytes(range(2,18)),1795200000),-60,9)
        self.assertEqual(self.store.history(cid),[])
        await backend.engine.node.dispatcher._process_received_packet(wire(KEY,1795200001),-60,9)
        history=self.store.history(cid);self.assertEqual(len(history),1);self.assertEqual(history[0]['text'],'private fixture')
        self.assertEqual(self.store.history('public'),[])
        backend.engine._send_packet=AsyncMock(return_value=True)
        await backend.engine.send_channel_message(backend.channels[cid],'outbound fixture',timestamp=1795200002)
        packet=backend.engine._send_packet.await_args.args[0];payload=bytes(packet.get_payload())
        self.assertEqual(payload[:1],hashlib.sha256(KEY).digest()[:1]);self.assertEqual(payload[1:3],hmac.digest(KEY,payload[3:],'sha256')[:2])
        self.assertIn(b'Zero: outbound fixture',AES.new(KEY,AES.MODE_ECB).decrypt(payload[3:]))
        self.assertNotIn(b'outbound fixture',packet.write_to())

    def test_private_keys_survive_encrypted_backup_and_bad_duplicates_are_rejected(self):
        self.store.set('identity',SEED.hex());cid=join_private(self.store,'Family',KEY.hex());self.store.add(cid,'Fixture','private history')
        path=backup.export(self.tmp.name,'disposable password');self.assertNotIn(KEY.hex().encode(),path.read_bytes())
        data=backup.read(path,'disposable password');self.store.leave(cid);backup.apply_restore(self.store,data,'disposable password')
        self.assertEqual(self.store.history(cid)[0]['text'],'private history')
        self.assertEqual(next(c for c in self.store.chats() if c['id']==cid)['secret'],KEY.hex())
        bad=copy.deepcopy(data);row=next(r for r in bad['chats'] if r['id']==cid).copy();row['id']='private:'+'a'*32;bad['chats'].append(row)
        with self.assertRaises(ValueError):backup.validate(bad)
    def test_private_channel_respects_slot_limit_but_existing_key_can_be_opened(self):
        cid=join_private(self.store,'Family',KEY.hex())
        for i in range(30):self.store.join('#topic'+str(i))
        self.assertEqual(len(self.store.chats()),32);self.assertEqual(join_private(self.store,'Another',KEY.hex()),cid)
        with self.assertRaisesRegex(ValueError,'limit'):join_private(self.store,'New',bytes(range(2,18)).hex())
