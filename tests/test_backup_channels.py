import copy
import hashlib
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor'))
from meshcore_zero import backup,identity_keys
from meshcore_zero.store import Store
from meshcore_zero.ui import UI
from meshcore_zero.radio import Backend
from openhop_core import CompanionRadio,LocalIdentity
from openhop_core.protocol import Packet
from openhop_core.protocol.transport_keys import calc_transport_code,get_auto_key_for
PASSWORD='fixture password only'
SEED=bytes(range(32))

class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);self.addCleanup(self.store.db.close);self.ui=UI(self.store)
        self.store.set('identity',SEED.hex());self.store.set('region','SCO')
        self.store.join('#testing');self.store.set_scope('#testing','ioi');self.store.mute('#testing',True)
        self.store.add('#testing','Fixture','Private saved message',unread=True,token='fixture')
        self.ui.repeater_passwords.save('ab'*32,'private repeater password')

    def test_encrypted_roundtrip_restores_identity_scopes_history_credentials_and_recovery(self):
        path=backup.export(self.tmp.name,PASSWORD)
        self.assertEqual(path.stat().st_mode&0o777,0o600)
        self.assertNotIn(SEED.hex().encode(),path.read_bytes());self.assertNotIn(b'Private saved message',path.read_bytes())
        data=backup.read(path,PASSWORD)
        self.assertEqual(backup.summary(data)['messages'],1)
        self.store.set('identity',bytes(range(32,64)).hex());self.store.set('region','US');self.store.leave('#testing')
        self.ui.repeater_passwords.forget('ab'*32)
        recovery=backup.apply_restore(self.store,data,PASSWORD)
        self.assertEqual(self.store.get('identity'),SEED.hex());self.assertEqual(self.store.get('region'),'SCO')
        self.assertTrue(self.store.is_muted('#testing'));self.assertEqual(self.store.history('#testing')[0]['text'],'Private saved message')
        self.assertEqual(self.store.db.execute("SELECT scope FROM chats WHERE id='#testing'").fetchone()[0],'ioi')
        self.assertEqual(self.ui.repeater_passwords.get('ab'*32),'private repeater password')
        previous=backup.read(recovery,PASSWORD)
        self.assertEqual(dict((r['key'],r['value']) for r in previous['settings'])['region'],'US')
        self.assertFalse(any(r['id']=='#testing' for r in previous['chats']))
        # A fresh device gets a different local credential key, but the password survives.
        with tempfile.TemporaryDirectory() as target:
            s=Store(target);u=UI(s)
            try:
                backup.apply_restore(s,data,PASSWORD)
                self.assertEqual(u.repeater_passwords.get('ab'*32),'private repeater password')
            finally:s.db.close()

    def test_wrong_password_tampering_and_invalid_content_leave_current_data_untouched(self):
        path=backup.export(self.tmp.name,PASSWORD)
        with self.assertRaisesRegex(ValueError,'Wrong password'):backup.read(path,'incorrect password')
        raw=bytearray(path.read_bytes());raw[-1]^=1;path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError,'damaged'):backup.read(path,PASSWORD)
        data=backup.snapshot(self.tmp.name);data['chats'][0]['scope']='*'
        with self.assertRaises(ValueError):backup.apply_restore(self.store,data,PASSWORD)
        self.assertEqual(self.store.get('identity'),SEED.hex());self.assertEqual(len(self.store.history('#testing')),1)

    def test_transaction_failure_rolls_back_all_tables_and_preserves_local_passwords(self):
        data=backup.snapshot(self.tmp.name)
        self.store.set('name','Current name')
        self.store.db.execute("CREATE TRIGGER reject_restore BEFORE INSERT ON chats BEGIN SELECT RAISE(ABORT,'fixture'); END")
        self.store.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):backup.apply_restore(self.store,data,PASSWORD)
        self.assertEqual(self.store.get('name'),'Current name');self.assertEqual(len(self.store.history('#testing')),1)
        self.assertEqual(self.ui.repeater_passwords.get('ab'*32),'private repeater password')
        self.assertTrue(list((Path(self.tmp.name)/'backups').glob('before-restore-*.mczb')))

    def test_regular_file_limits_and_schema_constraints(self):
        path=backup.export(self.tmp.name,PASSWORD);link=Path(self.tmp.name)/'link';link.symlink_to(path)
        with self.assertRaises(OSError):backup.read(link,PASSWORD)
        data=backup.snapshot(self.tmp.name)
        for mutate in (lambda d:d.update(format=99),lambda d:d['messages'][0].update(chat='missing'),lambda d:d['chats'].append(d['chats'][0].copy()),lambda d:d['settings'].append({'key':'region','value':'INVALID'})):
            bad=copy.deepcopy(data);mutate(bad)
            with self.assertRaises(ValueError):backup.validate(bad)

class MenuTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);self.addCleanup(self.store.db.close);self.ui=UI(self.store)
        self.store.set('identity',SEED.hex());self.store.join('#testing');self.store.add('#testing','Fixture','Keep')
        self.ui.selected=next(i for i,c in enumerate(self.store.chats()) if c['id']=='#testing')

    async def test_mute_scope_and_clear_cancel_confirm(self):
        await self.ui.key('backspace');self.assertEqual(self.ui.screen,'channel_options')
        self.assertEqual(self.ui.active_tab(),0)
        await self.ui.key('enter');self.assertTrue(self.store.is_muted('#testing'))
        await self.ui.key('down');await self.ui.key('enter')
        for c in '#eng-ne':await self.ui.key(c)
        await self.ui.key('enter');self.assertEqual(self.store.chats()[0]['scope'],'eng-ne')
        await self.ui.key('down');await self.ui.key('enter');self.assertEqual(self.ui.channel_ui.choice,1)
        self.ui.render();await self.ui.key('enter');self.assertEqual(len(self.store.history('#testing')),1)
        await self.ui.key('enter');await self.ui.key('tab');await self.ui.key('enter')
        self.assertEqual(self.store.history('#testing'),[]);self.assertTrue(self.store.is_muted('#testing'))
        self.assertTrue(self.store.db.execute("SELECT 1 FROM chats WHERE id='#testing'").fetchone())

    async def test_muted_channel_still_receives_history_and_unread_but_no_sound_or_toast(self):
        notify=AsyncMock();sound=AsyncMock();backend=Backend(self.store,notify,sound)
        backend.engine=CompanionRadio(None,LocalIdentity(SEED));backend.sync_channels();self.store.mute('#testing',True)
        event=SimpleNamespace(channel_idx=backend.channels['#testing'],channel_name='#testing',text='Fixture: muted message',sender_name='Fixture',timestamp=1,packet_hash='muted')
        await backend.channel_message(event)
        self.assertEqual(len(self.store.history('#testing')),2);self.assertEqual(self.store.chats()[0]['unread'],1)
        notify.assert_not_called();sound.assert_not_called()

    async def test_channel_scope_does_not_leak_to_next_channel_or_advert(self):
        engine=CompanionRadio(None,LocalIdentity(SEED));engine.set_default_flood_scope('sco',get_auto_key_for('sco'))
        engine.set_channel(0,'#testing',hashlib.sha256(b'#testing').digest()[:16]);engine._send_packet=AsyncMock(return_value=True)
        await engine.send_channel_message(0,'Override',scope_key=get_auto_key_for('ioi'))
        await engine.send_channel_message(0,'Default');await engine.advertise()
        for call,scope in zip(engine._send_packet.await_args_list,('ioi','sco','sco')):
            pkt=Packet();pkt.read_from(call.args[0].write_to())
            self.assertEqual(pkt.transport_codes[0],calc_transport_code(get_auto_key_for(scope),pkt))
        self.assertEqual(engine.get_default_flood_scope()[0],'sco')

    async def test_backup_ui_masks_password_confirm_defaults_cancel_and_queues_no_real_restore(self):
        self.ui.screen='settings';self.ui.selected=7;await self.ui.key('enter')
        await self.ui.key('enter')
        for c in PASSWORD:await self.ui.key(c)
        with patch.object(self.ui.text,'draw',wraps=self.ui.text.draw) as draw:self.ui.render()
        self.assertNotIn(PASSWORD,str(draw.call_args_list));self.assertNotIn(PASSWORD,str(self.ui.render_key()))
        await self.ui.key('enter');self.assertEqual(self.ui.backup_ui.state,'repeat')
        for c in PASSWORD:await self.ui.key(c)
        await self.ui.key('enter');await __import__('asyncio').gather(*self.ui.tasks)
        self.assertEqual(self.ui.backup_ui.state,'done')
        path=self.ui.backup_ui.path
        self.ui.backup_ui.password=PASSWORD;self.ui.backup_ui.path=path
        await self.ui.backup_ui.work('read');self.assertEqual(self.ui.backup_ui.choice,1)
        await self.ui.key('enter');self.assertIsNone(self.ui.pending_restore)
        self.ui.backup_ui.password=PASSWORD;await self.ui.backup_ui.work('read')
        await self.ui.key('tab');await self.ui.key('enter')
        self.assertTrue(self.ui.restart_requested);self.assertIsNotNone(self.ui.pending_restore)
        self.assertEqual(self.store.get('identity'),SEED.hex()) # only central shutdown may replace it
