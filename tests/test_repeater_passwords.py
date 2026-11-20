import tempfile
from pathlib import Path
import unittest
from unittest.mock import AsyncMock,patch
from meshcore_zero.store import Store
from meshcore_zero.ui import UI
from meshcore_zero.repeater_passwords import RepeaterPasswords

KEY='ab'*32
OTHER='cd'*32

class PasswordTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);self.addCleanup(self.store.db.close)
        self.ui=UI(self.store);self.ui.screen='repeater';self.ui.repeater={'public_key':KEY,'name':'Test repeater'}
        self.ui.repeater_state='password';self.ui.backend=object()

    async def test_opt_in_saves_encrypted_only_after_success_then_reuses_and_forgets(self):
        for c in 'example':await self.ui.key(c)
        await self.ui.key('enter');self.assertEqual(self.ui.repeater_state,'save');self.assertEqual(self.ui.repeater_choice,1)
        self.assertIsNone(self.ui.repeater_passwords.get(KEY))
        self.ui.render()
        await self.ui.key('tab')
        with patch('meshcore_zero.repeater.request_status',new=AsyncMock(return_value=({},None))):
            await self.ui.key('enter');await self.ui.repeater_task
        passwords=RepeaterPasswords(self.store)
        self.assertEqual(passwords.get(KEY),'example');self.assertIsNone(passwords.get(OTHER))
        self.assertEqual(passwords.key_path.stat().st_mode&0o777,0o600)
        blob=self.store.db.execute('SELECT encrypted FROM repeater_passwords').fetchone()[0]
        self.assertNotIn(b'example',blob)
        self.ui.repeater_state='confirm';self.ui.repeater_choice=0
        with patch('meshcore_zero.repeater.request_status',new=AsyncMock(return_value=({},None))) as request:
            await self.ui.key('enter');await self.ui.repeater_task
        request.assert_awaited_once_with(self.ui.backend,KEY,'example')
        await self.ui.key('backspace');self.assertIsNone(passwords.get(KEY))

    async def test_no_failed_and_cancelled_requests_do_not_save(self):
        self.ui.repeater_password='example';await self.ui.key('enter')
        with patch('meshcore_zero.repeater.request_status',new=AsyncMock(return_value=({},None))):
            await self.ui.key('enter');await self.ui.repeater_task
        self.assertIsNone(self.ui.repeater_passwords.get(KEY))
        self.ui.repeater_state='password';self.ui.repeater_password='wrong';await self.ui.key('enter');await self.ui.key('tab')
        with patch('meshcore_zero.repeater.request_status',new=AsyncMock(side_effect=ValueError('Login failed'))):
            await self.ui.key('enter');await self.ui.repeater_task
        self.assertIsNone(self.ui.repeater_passwords.get(KEY));self.assertEqual(self.ui.repeater_state,'error')
        self.ui.repeater_state='password';self.ui.repeater_password='cancel';await self.ui.key('enter');await self.ui.key('escape')
        self.assertEqual(self.ui.repeater_password,'');self.assertIsNone(self.ui.repeater_passwords.get(KEY))

    def test_persistence_missing_key_and_corrupt_ciphertext(self):
        passwords=self.ui.repeater_passwords;passwords.save(KEY,'example')
        reopened=Store(self.tmp.name)
        try:self.assertEqual(RepeaterPasswords(reopened).get(KEY),'example')
        finally:reopened.db.close()
        with self.store.db:self.store.db.execute('UPDATE repeater_passwords SET encrypted=?',(b'bad',))
        self.assertIsNone(passwords.get(KEY));passwords.save(KEY,'example')
        passwords.key_path.unlink();self.assertIsNone(passwords.get(KEY))
