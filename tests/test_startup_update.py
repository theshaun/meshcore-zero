import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from meshcore_zero.startup_update import available_release, check_at_startup
from meshcore_zero.store import Store
from meshcore_zero.ui import UI
from meshcore_zero.update import REPO

RELEASE=('99.0.0','meshcore-zero_99.0.0_arm64.deb',REPO+'/releases/download/v99.0.0/meshcore-zero_99.0.0_arm64.deb',REPO+'/releases/download/v99.0.0/SHA256SUMS')

class StartupTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);self.addCleanup(self.store.db.close)
        self.ui=UI(self.store)

    async def test_new_release_defaults_to_update_and_enters_existing_download_flow(self):
        with patch('meshcore_zero.startup_update.available_release',new=AsyncMock(return_value=RELEASE)):
            await check_at_startup(self.ui)
        self.assertEqual(self.ui.startup_update_choice,0)
        self.assertEqual(self.ui.render().size,(320,170))
        with patch.object(self.ui,'start_update') as start:
            await self.ui.key('enter')
        start.assert_called_once_with('download')
        self.assertEqual(self.ui.updater.release,RELEASE)
        self.assertEqual(self.ui.screen,'update');self.assertIsNone(self.ui.startup_release)

    async def test_later_and_escape_leave_chat_draft_and_navigation_intact(self):
        self.ui.open_chat(self.store.chats()[0]);self.ui.draft='unsent x'
        for keys in [('tab','enter'),('escape',)]:
            self.ui.startup_release=RELEASE;self.ui.startup_update_choice=0
            with patch.object(self.ui,'start_update') as start:
                for key in keys:await self.ui.key(key)
            start.assert_not_called();self.assertIsNone(self.ui.startup_release)
            self.assertEqual(self.ui.draft,'unsent x');self.assertEqual(self.ui.screen,'chat')

    async def test_offline_current_or_explicit_update_has_no_popup(self):
        for screen,release in [('inbox',None),('update',RELEASE)]:
            self.ui.screen=screen
            with patch('meshcore_zero.startup_update.available_release',new=AsyncMock(return_value=release)):
                await check_at_startup(self.ui)
            self.assertIsNone(self.ui.startup_release)

    async def test_radio_preflight_takes_priority(self):
        self.ui.launch_state='conflict'
        with patch('meshcore_zero.startup_update.available_release',new=AsyncMock(return_value=RELEASE)):
            task=asyncio.create_task(check_at_startup(self.ui));await asyncio.sleep(0)
            self.assertIsNone(self.ui.startup_release)
            self.ui.launch_state='';await task
        self.assertEqual(self.ui.startup_release,RELEASE)

    async def test_worker_success_and_unavailable_results(self):
        for payload,result in [(json.dumps(RELEASE).encode(),list(RELEASE)),(b'null',None),(b'invalid',None)]:
            process=SimpleNamespace(returncode=0,communicate=AsyncMock(return_value=(payload,b'')))
            with patch('meshcore_zero.startup_update.asyncio.create_subprocess_exec',new=AsyncMock(return_value=process)):
                self.assertEqual(await available_release(),result)

    async def test_worker_timeout_and_exit_cancel_reap_child(self):
        for error in (asyncio.TimeoutError,asyncio.CancelledError):
            process=SimpleNamespace(returncode=None)
            process.kill=lambda:setattr(process,'returncode',-9)
            process.communicate=AsyncMock(side_effect=[error(),(b'',b'')])
            with patch('meshcore_zero.startup_update.asyncio.create_subprocess_exec',new=AsyncMock(return_value=process)):
                if error is asyncio.CancelledError:
                    with self.assertRaises(asyncio.CancelledError):await available_release()
                else:self.assertIsNone(await available_release())
            self.assertEqual(process.returncode,-9)
            self.assertEqual(process.communicate.await_count,2)
