"""Editable region scopes/path hashes; all packets stay off air."""
import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor'))
from openhop_core import CompanionRadio,LocalIdentity
from openhop_core.protocol import Packet
from openhop_core.protocol.transport_keys import calc_transport_code,get_auto_key_for
from meshcore_zero import backup
from meshcore_zero.regions import protocol_config,configure_protocol,active_scope
from meshcore_zero.store import Store
from meshcore_zero.ui import UI


class ProtocolSettingsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);self.addCleanup(self.store.db.close)
        self.ui=UI(self.store)

    async def test_settings_entry_edit_cancel_unscoped_cycle_and_reset(self):
        u=self.ui;s=self.store;s.set('region','SCO')
        u.screen='settings';u.selected=8;await u.key('down');await u.key('enter')
        self.assertEqual(u.screen,'protocol');self.assertEqual(u.active_tab(),4)
        self.assertEqual(protocol_config(s),('sco',3));self.assertEqual(u.render().size,(320,170))
        before=u.render_key();await u.key('enter');await u.key('x')
        self.assertNotEqual(u.render_key(),before)
        await u.key('escape');self.assertIsNone(s.get('scope_SCO'))
        await u.key('enter');u.protocol_ui.input=' #Eng-NE ';await u.key('enter')
        self.assertEqual(protocol_config(s),('eng-ne',3))
        await u.key('enter');u.protocol_ui.input='bad scope';await u.key('enter')
        self.assertEqual(u.protocol_ui.state,'scope');self.assertEqual(s.get('scope_SCO'),'eng-ne')
        u.protocol_ui.input='';await u.key('enter')
        self.assertEqual(protocol_config(s),('',3))  # Explicit unscoped overrides sco.
        await u.key('down');await u.key('enter');self.assertEqual(protocol_config(s),('',1))
        await u.key('right');self.assertEqual(protocol_config(s),('',2))
        await u.key('left');self.assertEqual(protocol_config(s),('',1))
        # Overrides are per preset and persist after reopening storage.
        s.set('region','US');self.assertEqual(protocol_config(s),('',1))
        s.set('region','SCO')
        second=Store(self.tmp.name)
        try:self.assertEqual(protocol_config(second),('',1))
        finally:second.db.close()
        await u.key('down');await u.key('enter')
        self.assertEqual(protocol_config(s),('sco',3));self.assertIsNone(s.get('path_bytes_SCO'))
        await u.key('escape');self.assertEqual((u.screen,u.selected),('settings',9))

    async def test_all_sizes_and_scopes_reach_encoded_messages_and_startup_adverts(self):
        s=self.store;s.set('region','US')
        engine=CompanionRadio(None,LocalIdentity(bytes(range(32))))
        engine.set_channel(0,'#testing',hashlib.sha256(b'#testing').digest()[:16])
        engine._send_packet=AsyncMock(return_value=True)
        for size in (1,2,3):
            for scope in ('eng-ne',''):
                s.set('path_bytes_US',size);s.set('scope_US',scope)
                configure_protocol(engine,'US',s)
                engine._send_packet.reset_mock()
                await engine.send_channel_message(0,'offline test');await engine.advertise(flood=True)
                for call in engine._send_packet.await_args_list:
                    packet=Packet();self.assertTrue(packet.read_from(call.args[0].write_to()))
                    self.assertEqual(packet.get_path_hash_size(),size)
                    self.assertEqual(packet.get_route_type(),0 if scope else 1)
                    if scope:self.assertEqual(packet.transport_codes[0],calc_transport_code(get_auto_key_for(scope),packet))
        s.set('scope_US','eng-ne');configure_protocol(engine,'US',s)
        engine._send_packet.reset_mock()
        await engine.send_channel_message(0,'override',scope_key=get_auto_key_for('ioi'))
        await engine.advertise(flood=True)
        for call,scope in zip(engine._send_packet.await_args_list,('ioi','eng-ne')):
            packet=call.args[0]
            self.assertEqual(packet.transport_codes[0],calc_transport_code(get_auto_key_for(scope),packet))
        self.assertEqual(engine.get_default_flood_scope()[0],'eng-ne')

    async def test_pending_changes_do_not_mislabel_live_chat_or_default_channel_scope(self):
        from types import SimpleNamespace
        s=self.store;s.set('region','SCO');s.join('#testing')
        engine=CompanionRadio(None,LocalIdentity(bytes(range(32))));configure_protocol(engine,'SCO',s)
        u=self.ui;u.backend=SimpleNamespace(engine=engine,region='SCO',state='Ready',error='')
        s.set('scope_SCO','new-scope')
        self.assertEqual(active_scope(s,u.backend),'sco')
        chat=next(c for c in s.chats() if c['id']=='#testing');u.channel_ui.open(chat)
        with patch.object(u.text,'draw',wraps=u.text.draw) as draw:
            u.render();self.assertTrue(any('Default · sco' in str(c) for c in draw.call_args_list))
        u.open_chat(chat)
        with patch.object(u.text,'draw',wraps=u.text.draw) as draw:
            u.render();self.assertTrue(any('Scope: sco' in str(c) for c in draw.call_args_list))
        configure_protocol(engine,'SCO',s);self.assertEqual(active_scope(s,u.backend),'new-scope')

    async def test_encrypted_backup_roundtrip_and_invalid_settings_rejected(self):
        s=self.store;s.set('identity',bytes(range(32)).hex());s.set('region','SCO')
        s.set('scope_SCO','');s.set('path_bytes_SCO',2);s.set('scope_US','eng-ne')
        path=backup.export(self.tmp.name,'disposable password')
        data=backup.read(path,'disposable password')
        s.set('scope_SCO','changed');s.set('path_bytes_SCO',1)
        backup.apply_restore(s,data,'disposable password')
        self.assertEqual(protocol_config(s),('',2));self.assertEqual(protocol_config(s,'US'),('eng-ne',1))
        for key,value in (('scope_SCO','a b'),('scope_SCO','#raw'),('scope_SCO','x'*31),('path_bytes_SCO','4'),('path_bytes_XX','2'),('scope_XX','sco')):
            bad=copy.deepcopy(data)
            bad['settings']=[r for r in bad['settings'] if r['key']!=key]+[{'key':key,'value':value}]
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):backup.validate(bad)
