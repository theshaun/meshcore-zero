import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from meshcore_zero.screen_idle import ScreenIdle
from meshcore_zero.sound import MessageSound
from meshcore_zero.store import Store
from meshcore_zero.radio import Backend
from meshcore_zero.ui import UI


class ScreenTests(unittest.IsolatedAsyncioTestCase):
    async def test_system_timeout_wake_never_and_exit_preserve_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);config=root/'config.json';light=root/'brightness'
            original=json.dumps({'dark_time':10,'brightness':40,'other':'preserve'})
            config.write_text(original);light.write_text('40');now=[0]
            screen=ScreenIdle(config,light,lambda:now[0]);screen.tick()
            now[0]=9;screen.tick();self.assertEqual(light.read_text(),'40')
            now[0]=10;screen.tick();self.assertEqual(light.read_text(),'0')
            self.assertTrue(await screen.activity());self.assertEqual(light.read_text(),'40')
            self.assertFalse(await screen.activity())
            now[0]=20;screen.tick();await screen.close()
            self.assertEqual(light.read_text(),'40');self.assertEqual(config.read_text(),original)
            config.write_text('{"dark_time":0}');now[0]=22;screen.tick()
            now[0]=10000;screen.tick();self.assertEqual(light.read_text(),'40')
            config.write_text('{"dark_time":10}');now[0]=10002;screen.tick()
            self.assertEqual(light.read_text(),'0')
            config.write_text('{"dark_time":0}');now[0]=10004;screen.tick()
            self.assertEqual(light.read_text(),'40')

    async def test_missing_hardware_nonfatal_and_external_blank_not_owned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);light=root/'brightness';config=root/'config'
            screen=ScreenIdle(config,light);screen.tick();self.assertTrue(screen.failed)
            await screen.close()
            light.write_text('0');screen=ScreenIdle(config,light);screen.tick()
            await screen.close();self.assertEqual(light.read_text(),'0')
            self.assertTrue(await screen.activity());self.assertEqual(light.read_text(),'40')


class SoundTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);self.addCleanup(self.store.db.close)

    async def test_new_messages_only_not_duplicate_packets_or_echoes(self):
        calls=[];backend=Backend(self.store,lambda _:None,lambda:calls.append('chime'))
        self.store.join('#testing');backend.channels={'#testing':1}
        backend.engine=SimpleNamespace(sync_next_message=lambda:None,get_contact_by_key=lambda _:SimpleNamespace(name='Test'))
        event=SimpleNamespace(channel_idx=1,text='Test: hello',sender_name='Test',timestamp=1,packet_hash='abc',channel_name='#testing')
        await backend.channel_message(event);await backend.channel_message(event)
        event=SimpleNamespace(sender_key=bytes.fromhex('aa'*32),text='DM',timestamp=2,packet_hash='def')
        await backend.direct_message(event);await backend.direct_message(event)
        self.assertEqual(calls,['chime','chime'])

    async def test_mute_burst_collapse_and_child_cleanup(self):
        sound=MessageSound(self.store);sound.player='/usr/bin/paplay'
        self.store.set('message_sound','off');sound.received();self.assertIsNone(sound.task)
        self.store.set('message_sound','on')
        started=asyncio.Event()
        async def wait():
            if process.returncode is not None:
                return process.returncode
            started.set();await asyncio.Event().wait()
        process=SimpleNamespace(returncode=None,kill=lambda:setattr(process,'returncode',-9))
        process.wait=AsyncMock(side_effect=wait)
        with patch('meshcore_zero.sound.asyncio.create_subprocess_exec',new=AsyncMock(return_value=process)) as create:
            sound.received();task=sound.task;sound.received();self.assertIs(sound.task,task)
            await started.wait();await sound.close()
            self.assertEqual(process.returncode,-9);create.assert_awaited_once()

    async def test_sound_setting_is_reachable_and_persists(self):
        ui=UI(self.store);ui.screen='settings';ui.selected=4
        await ui.key('down');await ui.key('enter')
        self.assertEqual(self.store.get('message_sound'),'off')
        self.assertEqual(ui.render().size,(320,170))
