import asyncio
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor'))
from meshcore_zero.store import Store,PUBLIC_KEY
from meshcore_zero.ui import UI
from meshcore_zero.radio import Backend
from meshcore_zero import identity_keys as keys
from openhop_core import LocalIdentity,CompanionRadio

# Disposable deterministic identities, never device identity material.
SEED=bytes(range(32));OTHER=bytes(range(32,64))

class ChannelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);self.addCleanup(self.store.db.close);self.ui=UI(self.store)

    async def test_cancel_default_and_confirm_only_target_channel_even_if_list_moves(self):
        self.store.join('#testing');self.store.add('#testing','Test','keep',token='keep')
        self.store.join('#leave-test');self.store.add('#leave-test','Test','remove',token='remove')
        self.ui.selected=next(i for i,c in enumerate(self.store.chats()) if c['id']=='#leave-test')
        await self.ui.key('backspace');self.assertEqual(self.ui.leave_choice,1)
        self.assertEqual(self.ui.render().size,(320,170));await self.ui.key('enter')
        self.assertIsNone(self.ui.leave_target);self.assertEqual(len(self.store.history('#leave-test')),1)
        await self.ui.key('backspace')
        self.store.add('#testing','Test','newer',timestamp=9999999999)
        await self.ui.key('tab');await self.ui.key('enter')
        self.assertNotIn('#leave-test',[c['id'] for c in self.store.chats()]);self.assertEqual(self.store.history('#leave-test'),[])
        self.assertEqual(len(self.store.history('#testing')),2)

    async def test_public_stays_left_after_restart_and_can_be_rejoined(self):
        self.store.leave('public')
        reopened=Store(self.tmp.name)
        try:self.assertEqual(reopened.chats(),[])
        finally:reopened.db.close()
        await self.ui.key('tab');await self.ui.key('down');await self.ui.key('enter')
        self.assertEqual(self.ui.chat['id'],'public');self.assertEqual(self.ui.chat['secret'],PUBLIC_KEY)

    async def test_dm_backspace_does_not_offer_channel_leave(self):
        self.store.dm('a'*64,'Contact');self.ui.selected=next(i for i,c in enumerate(self.store.chats()) if c['kind']=='dm')
        await self.ui.key('backspace');self.assertIsNone(self.ui.leave_target)

    async def test_engine_keys_removed_and_other_indices_stay_valid(self):
        self.store.join('#leave-test');self.store.join('#testing')
        backend=Backend(self.store);backend.engine=CompanionRadio(SimpleNamespace(),LocalIdentity(SEED))
        backend.sync_channels();idx=backend.channels['#testing'];removed=backend.channels['#leave-test']
        backend.leave_channel('#leave-test')
        self.assertEqual(backend.channels['#testing'],idx);self.assertIsNone(backend.engine.get_channel(removed))
        self.assertEqual(backend.engine.get_channel(idx).name,'#testing')
        self.store.join('#new');backend.sync_channels();self.assertEqual(backend.channels['#new'],removed)
        event=SimpleNamespace(channel_idx=idx,channel_name='#testing',text='Test: receive after leaving',sender_name='Test',timestamp=1,packet_hash='received')
        await backend.channel_message(event)
        self.assertEqual(self.store.history('#testing')[0]['text'],'receive after leaving')
        async with backend.send_lock:
            with self.assertRaisesRegex(ValueError,'Radio busy'):backend.leave_channel('#testing')
        backend.engine=None

    async def test_identity_import_preview_cancel_apply_restore_and_history_survive(self):
        self.store.set('identity',SEED.hex());self.store.join('#testing')
        self.store.add('#testing','Test','history');self.ui.repeater_passwords.save('ab'*32,'fixture')
        self.ui.screen='settings';self.ui.selected=6;await self.ui.key('enter')
        self.assertEqual(self.ui.screen,'identity');await self.ui.key('enter')
        text=keys.firmware_key(OTHER).hex()
        for char in text:await self.ui.key(char)
        with patch.object(self.ui.text,'draw',wraps=self.ui.text.draw) as draw:self.ui.render()
        self.assertNotIn(text,str(draw.call_args_list))
        await self.ui.key('enter');self.assertEqual(self.ui.identity_ui.state,'confirm')
        self.assertEqual(self.ui.identity_ui.choice,1);self.ui.render();await self.ui.key('enter')
        self.assertEqual(self.store.get('identity'),SEED.hex())
        self.ui.identity_ui.stage(keys.firmware_key(OTHER));await self.ui.key('tab');await self.ui.key('enter')
        self.assertTrue(self.ui.restart_requested);self.assertFalse(self.ui.running)
        self.assertEqual(self.store.get('identity_backup'),SEED.hex())
        self.assertEqual(self.ui.repeater_passwords.get('ab'*32),'fixture')
        self.assertEqual(len(self.store.history('#testing')),1)
        restored=UI(self.store);restored.identity_ui.open();restored.identity_ui.selected=3
        await restored.key('enter');self.assertEqual(restored.identity_ui.preview,keys.public_key(SEED))
        await restored.key('tab');await restored.key('enter')
        self.assertEqual(keys.public_key(keys.stored_key(self.store.get('identity'))),keys.public_key(SEED))

    async def test_file_import_and_export_require_confirmation_and_keep_secrets_off_screen(self):
        self.store.set('identity',SEED.hex());self.ui.identity_ui.open();self.ui.identity_ui.selected=1
        file=Path(self.tmp.name)/'identity-import.txt';file.write_text(keys.firmware_key(OTHER).hex())
        await self.ui.key('enter');await self.ui.key('enter')
        self.assertEqual(self.ui.identity_ui.state,'confirm');await self.ui.key('escape')
        self.assertEqual(self.store.get('identity'),SEED.hex())
        self.ui.identity_ui.selected=2;await self.ui.key('enter')
        export=Path(self.tmp.name)/'identity-export.txt'
        self.assertFalse(export.exists());await self.ui.key('enter');self.assertFalse(export.exists())
        await self.ui.key('enter');await self.ui.key('tab');await self.ui.key('enter')
        self.assertTrue(export.exists());self.assertEqual(export.stat().st_mode&0o777,0o600)
        with patch.object(self.ui.text,'draw',wraps=self.ui.text.draw) as draw:self.ui.render()
        self.assertNotIn(export.read_text().strip(),str(draw.call_args_list))

class KeyTests(unittest.TestCase):
    def test_seed_expansion_matches_signatures_public_key_and_shared_secrets(self):
        expanded=keys.firmware_key(SEED)
        seed=LocalIdentity(SEED);firmware=LocalIdentity(expanded);peer=LocalIdentity(OTHER)
        self.assertEqual(keys.public_key(SEED),keys.public_key(expanded))
        self.assertEqual(seed.sign(b'test'),firmware.sign(b'test'))
        self.assertEqual(peer.calc_shared_secret(seed.get_private_key()),peer.calc_shared_secret(firmware.get_private_key()))
        self.assertEqual(keys.parse_firmware(' \n'+expanded.hex().upper()+'\n'),expanded)

    def test_libsodium_seed_public_pair_is_rejected(self):
        from nacl.signing import SigningKey
        seed=bytes([8])+bytes(30)+bytes([64])
        pair=seed+SigningKey(seed).verify_key.encode()
        with self.assertRaises(ValueError):keys.parse_firmware(pair.hex())

    def test_bad_lengths_hex_and_incompatible_expanded_scalars_are_rejected(self):
        for text in ('x'*128,'ab'*32,'00'*64,(SEED+LocalIdentity(SEED).get_public_key()).hex()):
            with self.assertRaises(ValueError):keys.parse_firmware(text)

    def test_private_export_roundtrip_and_atomic_replacement_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp)
            try:
                store.set('identity',SEED.hex());store.join('#testing');store.add('#testing','Test','saved')
                path=keys.export_key(store)
                self.assertEqual(path.stat().st_mode&0o777,0o600);self.assertEqual(len(path.read_text().strip()),128)
                self.assertEqual(keys.public_key(keys.read_key_file(path)),keys.public_key(SEED))
                self.assertTrue(keys.replace_identity(store,keys.firmware_key(OTHER)))
                self.assertEqual(store.get('identity_backup'),SEED.hex());self.assertEqual(len(store.history('#testing')),1)
                self.assertEqual(keys.public_key(keys.stored_key(store.get('identity'))),keys.public_key(OTHER))
                self.assertFalse(keys.replace_identity(store,keys.firmware_key(OTHER)))
                self.assertEqual(store.get('identity_backup'),SEED.hex())
            finally:store.db.close()

    def test_file_import_rejects_nonregular_symlink_or_oversized_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/'key';target.write_text(keys.firmware_key(SEED).hex())
            link=root/'link';link.symlink_to(target)
            with self.assertRaises(OSError):keys.read_key_file(link)
            target.write_text('a'*4097)
            with self.assertRaises(ValueError):keys.read_key_file(target)

class IdentityUiTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);self.addCleanup(self.store.db.close)
        self.store.set('identity',SEED.hex());self.ui=UI(self.store);self.ui.screen='settings';self.ui.selected=6

    async def test_import_cancel_then_confirm_preserves_history_and_requests_restart(self):
        self.store.join('#testing');self.store.add('#testing','Test','keep')
        await self.ui.key('enter');self.assertEqual(self.ui.screen,'identity')
        await self.ui.key('enter');encoded=keys.firmware_key(OTHER).hex()
        for char in encoded:await self.ui.key(char)
        with patch.object(self.ui.text,'draw',wraps=self.ui.text.draw) as draw:self.ui.render()
        self.assertNotIn(encoded,str(draw.call_args_list))
        await self.ui.key('enter');self.assertEqual(self.ui.identity_ui.choice,1)
        self.assertEqual(self.ui.render().size,(320,170));await self.ui.key('enter')
        self.assertEqual(self.store.get('identity'),SEED.hex())
        self.ui.identity_ui.stage(keys.firmware_key(OTHER));await self.ui.key('tab');await self.ui.key('enter')
        self.assertTrue(self.ui.restart_requested);self.assertFalse(self.ui.running)
        self.assertEqual(self.store.get('identity_backup'),SEED.hex());self.assertEqual(len(self.store.history('#testing')),1)

    async def test_export_requires_confirmation_and_never_renders_secret(self):
        await self.ui.key('enter');self.ui.identity_ui.selected=2;await self.ui.key('enter')
        await self.ui.key('enter');self.assertFalse((Path(self.tmp.name)/'identity-export.txt').exists())
        await self.ui.key('enter');await self.ui.key('tab');await self.ui.key('enter')
        self.assertEqual(self.ui.identity_ui.state,'export_done')
        with patch.object(self.ui.text,'draw',wraps=self.ui.text.draw) as draw:self.ui.render()
        self.assertNotIn(keys.firmware_key(SEED).hex(),str(draw.call_args_list))
