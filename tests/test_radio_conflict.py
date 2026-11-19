import asyncio
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,patch
from meshcore_zero.radio_conflict import is_running,stop_service,start_radio,ServiceError,command,SYSTEMCTL,UNIT
from meshcore_zero.store import Store
from meshcore_zero.ui import UI

class ConflictTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);self.addCleanup(self.store.db.close)
        self.ui=UI(self.store)
        self.backend=SimpleNamespace(start=AsyncMock(),state='Starting radio',error='')

    async def test_no_service_and_inactive_units_skip_notice(self):
        for code,output in [(1,'LoadState=not-found\nActiveState=inactive\nMainPID=0\n'),
                            (0,'LoadState=loaded\nActiveState=inactive\nMainPID=0\n')]:
            with patch('meshcore_zero.radio_conflict.command',new=AsyncMock(return_value=(code,output))):
                self.assertFalse(await is_running())
        check=AsyncMock(return_value=False);stop=AsyncMock()
        await start_radio(self.ui,self.backend,check,stop)
        self.backend.start.assert_awaited_once();stop.assert_not_awaited()
        self.assertEqual(self.ui.launch_state,'')

    async def test_active_and_transitioning_units_are_detected(self):
        for state in ('active','activating','deactivating','reloading'):
            with patch('meshcore_zero.radio_conflict.command',new=AsyncMock(return_value=(0,f'LoadState=loaded\nActiveState={state}\nMainPID=123\n'))):
                self.assertTrue(await is_running())
        for output in ('','LoadState=loaded\nActiveState=unknown\nMainPID=0\n','LoadState=error\n'):
            with patch('meshcore_zero.radio_conflict.command',new=AsyncMock(return_value=(1,output))):
                with self.assertRaises(ServiceError):await is_running()

    async def test_acknowledgement_precedes_stop_and_all_hardware_start(self):
        check=AsyncMock(side_effect=[True,False]);stop=AsyncMock()
        task=asyncio.create_task(start_radio(self.ui,self.backend,check,stop))
        await asyncio.sleep(0)
        self.assertEqual(self.ui.launch_state,'conflict')
        self.backend.start.assert_not_awaited();stop.assert_not_awaited()
        for key in ('tab','escape','left','down','a'):
            await self.ui.key(key)
        self.assertFalse(self.ui.launch_ack.is_set());self.assertTrue(self.ui.running)
        with patch.object(self.ui.text,'draw',wraps=self.ui.text.draw) as draw:
            self.ui.render()
        text=[c.args[2] for c in draw.call_args_list]
        self.assertEqual(text.count('Okay'),1);self.assertNotIn('Cancel',text)
        await self.ui.key('enter');await task
        stop.assert_awaited_once();self.backend.start.assert_awaited_once()
        self.assertEqual(self.ui.launch_state,'')

    async def test_stop_permission_failure_timeout_or_restart_never_opens_radio(self):
        for failure in (ServiceError('MeshZero could not be closed.'),ServiceError('MeshZero did not finish closing.')):
            ui=UI(self.store)
            # Clear happens after check; acknowledge after the dialog appears.
            task=asyncio.create_task(start_radio(ui,self.backend,AsyncMock(return_value=True),AsyncMock(side_effect=failure)))
            await asyncio.sleep(0);await ui.key('enter');await task
            self.assertEqual(ui.launch_state,'error');self.backend.start.assert_not_awaited()
            await ui.key('enter');self.assertFalse(ui.running)
        ui=UI(self.store)
        task=asyncio.create_task(start_radio(ui,self.backend,AsyncMock(return_value=True),AsyncMock()))
        await asyncio.sleep(0);await ui.key('enter');await task
        self.assertEqual(ui.launch_state,'error');self.backend.start.assert_not_awaited()

    async def test_check_failure_and_cancellation_do_not_hang_or_start_hardware(self):
        await start_radio(self.ui,self.backend,AsyncMock(side_effect=ServiceError('Cannot check')),AsyncMock())
        self.assertEqual(self.ui.launch_state,'error');self.backend.start.assert_not_awaited()
        ui=UI(self.store);stop=AsyncMock()
        task=asyncio.create_task(start_radio(ui,self.backend,AsyncMock(return_value=True),stop))
        await asyncio.sleep(0);task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        stop.assert_not_awaited();self.backend.start.assert_not_awaited()

    async def test_stop_targets_only_the_exact_meshzero_unit_and_verifies_exit(self):
        with patch('meshcore_zero.radio_conflict.command',new=AsyncMock(return_value=(0,''))) as run:
            with patch('meshcore_zero.radio_conflict.is_running',new=AsyncMock(return_value=False)):
                await stop_service()
            self.assertEqual(run.await_args.args,('/usr/bin/sudo','-n',SYSTEMCTL,'stop',UNIT))
        policy=Path('packaging/meshcore-zero-radio.sudoers').read_text()
        grants=[line for line in policy.splitlines() if line and not line.startswith('#')]
        self.assertEqual(grants,['%gpio ALL=(root) NOPASSWD: /usr/bin/systemctl stop meshzero.service'])

    async def test_subprocess_timeout_reaps_its_own_client(self):
        process=SimpleNamespace(returncode=None,kill=lambda:setattr(process,'killed',True),killed=False)
        process.communicate=AsyncMock(side_effect=[asyncio.CancelledError(),(b'',b'')])
        async def timed_out(coro,timeout):
            try:await coro
            except asyncio.CancelledError:raise asyncio.TimeoutError
        with patch('meshcore_zero.radio_conflict.asyncio.create_subprocess_exec',new=AsyncMock(return_value=process)):
            with patch('meshcore_zero.radio_conflict.asyncio.wait_for',side_effect=timed_out):
                with self.assertRaises(ServiceError):await command(SYSTEMCTL,'show',UNIT)
        self.assertTrue(process.killed)
