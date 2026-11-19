import asyncio
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,patch
from meshcore_zero.radio_conflict import is_running,start_radio,ServiceError,command,SYSTEMCTL,UNIT
from meshcore_zero.store import Store
from meshcore_zero.ui import UI

class ConflictTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);self.addCleanup(self.store.db.close)
        self.ui=UI(self.store)
        self.backend=SimpleNamespace(start=AsyncMock(),state='Starting radio',error='')

    async def test_no_service_or_inactive_service_starts_normally(self):
        for code,output in [(1,'LoadState=not-found\nActiveState=inactive\nMainPID=0\n'),
                            (0,'LoadState=loaded\nActiveState=inactive\nMainPID=0\n')]:
            with patch('meshcore_zero.radio_conflict.command',new=AsyncMock(return_value=(code,output))):
                self.assertFalse(await is_running())
        await start_radio(self.ui,self.backend,AsyncMock(return_value=False))
        self.backend.start.assert_awaited_once()
        self.assertEqual(self.ui.launch_state,'')

    async def test_active_and_transitioning_units_are_detected(self):
        for state in ('active','activating','deactivating','reloading'):
            with patch('meshcore_zero.radio_conflict.command',new=AsyncMock(return_value=(0,f'LoadState=loaded\nActiveState={state}\nMainPID=123\n'))):
                self.assertTrue(await is_running())
        for output in ('','LoadState=loaded\nActiveState=unknown\nMainPID=0\n','LoadState=error\n'):
            with patch('meshcore_zero.radio_conflict.command',new=AsyncMock(return_value=(1,output))):
                with self.assertRaises(ServiceError):await is_running()

    async def test_okay_rechecks_without_stopping_service_or_opening_radio(self):
        check=AsyncMock(side_effect=[True,True,False,False])
        task=asyncio.create_task(start_radio(self.ui,self.backend,check))
        await asyncio.sleep(0)
        self.assertEqual(self.ui.launch_state,'conflict');self.backend.start.assert_not_awaited()
        for key in ('tab','left','down','a'):await self.ui.key(key)
        self.assertFalse(self.ui.launch_ack.is_set())
        with patch.object(self.ui.text,'draw',wraps=self.ui.text.draw) as draw:self.ui.render()
        text=[c.args[2] for c in draw.call_args_list]
        self.assertEqual(text.count('Okay'),1)
        self.assertTrue(any('sudo systemctl stop meshzero.service' in s for s in text))
        await self.ui.key('enter');await asyncio.sleep(0)
        self.assertEqual(self.ui.launch_state,'conflict');self.backend.start.assert_not_awaited()
        # An external actor has now stopped MeshZero; Okay may proceed.
        await self.ui.key('enter');await task
        self.backend.start.assert_awaited_once();self.assertEqual(self.ui.launch_state,'')

    async def test_escape_exits_without_starting_hardware(self):
        task=asyncio.create_task(start_radio(self.ui,self.backend,AsyncMock(return_value=True)))
        await asyncio.sleep(0);await self.ui.key('escape');await task
        self.assertFalse(self.ui.running);self.backend.start.assert_not_awaited()

    async def test_check_failure_and_cancellation_do_not_hang_or_start_hardware(self):
        await start_radio(self.ui,self.backend,AsyncMock(side_effect=ServiceError('Cannot check')))
        self.assertEqual(self.ui.launch_state,'error');self.backend.start.assert_not_awaited()
        await self.ui.key('enter');self.assertFalse(self.ui.running)
        ui=UI(self.store)
        task=asyncio.create_task(start_radio(ui,self.backend,AsyncMock(return_value=True)))
        await asyncio.sleep(0);task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.backend.start.assert_not_awaited()

    async def test_service_checks_are_read_only(self):
        with patch('meshcore_zero.radio_conflict.command',new=AsyncMock(return_value=(0,'LoadState=loaded\nActiveState=inactive\nMainPID=0\n'))) as run:
            self.assertFalse(await is_running())
            self.assertEqual(run.await_args.args,(SYSTEMCTL,'show',UNIT,'--no-pager','--property=LoadState,ActiveState,MainPID'))
        self.assertFalse(Path('packaging/meshcore-zero-radio.sudoers').exists())

    async def test_subprocess_timeout_reaps_only_its_own_client(self):
        process=SimpleNamespace(returncode=None,kill=lambda:setattr(process,'killed',True),killed=False)
        process.communicate=AsyncMock(side_effect=[asyncio.CancelledError(),(b'',b'')])
        async def timed_out(coro,timeout):
            try:await coro
            except asyncio.CancelledError:raise asyncio.TimeoutError
        with patch('meshcore_zero.radio_conflict.asyncio.create_subprocess_exec',new=AsyncMock(return_value=process)):
            with patch('meshcore_zero.radio_conflict.asyncio.wait_for',side_effect=timed_out):
                with self.assertRaises(ServiceError):await command(SYSTEMCTL,'show',UNIT)
        self.assertTrue(process.killed)
