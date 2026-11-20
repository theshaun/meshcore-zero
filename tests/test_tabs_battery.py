import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from meshcore_zero.battery import read_capacity
from meshcore_zero.store import Store
from meshcore_zero.ui import UI, SELECT, TEXT

class BatteryTests(unittest.TestCase):
    def test_capacity_from_battery_only_and_unavailable_is_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);usb=root/'a-usb';usb.mkdir()
            (usb/'type').write_text('USB\n');(usb/'capacity').write_text('100')
            self.assertIsNone(read_capacity(root))
            battery=root/'gauge';battery.mkdir();(battery/'type').write_text('Battery\n')
            for value,expected in [('0',0),('42\n',42),('100',100),('101',None),('-1',None),('unknown',None)]:
                (battery/'capacity').write_text(value)
                self.assertEqual(read_capacity(root),expected)
            (battery/'capacity').unlink();self.assertIsNone(read_capacity(root))
        self.assertIsNone(read_capacity(root))

class TabTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);self.addCleanup(self.store.db.close)
        self.ui=UI(self.store)

    def test_tab_switches_pages_immediately_and_preserves_drafts(self):
        import asyncio
        async def scenario():
            for expected in ('join','nodes','map','settings','inbox'):
                await self.ui.key('tab')
                self.assertEqual(self.ui.screen,expected)
                self.assertEqual(self.ui.menu,-1)
            self.ui.open_chat(self.store.chats()[0]);self.ui.draft='x draft'
            await self.ui.key('tab');self.assertEqual(self.ui.screen,'join')
            self.ui.draft='#draft'
            for _ in range(5):await self.ui.key('tab')
            self.assertEqual(self.ui.draft,'#draft')
            self.ui.open_chat(self.store.chats()[0]);self.assertEqual(self.ui.draft,'x draft')
        asyncio.run(scenario())

    def test_current_section_highlight_in_nested_screens_and_centered_titles(self):
        for screen,index in [('inbox',0),('chat',0),('join',1),('nodes',2),('map',3),('map_details',3),('settings',4),('name',4),('regions',4),('update',4),('gps_sharing',4)]:
            self.ui.screen=screen
            self.assertEqual(self.ui.active_tab(),index)
        self.ui.screen='inbox'
        with patch.object(self.ui.text,'draw',wraps=self.ui.text.draw) as draw:
            frame=self.ui.render()
        labels=[c for c in draw.call_args_list if c.args[2] in ('Chats','Join','Nodes','Map','Settings')]
        self.assertEqual([c.args[2] for c in labels],['Chats','Join','Nodes','Map','Settings'])
        for index,call in enumerate(labels):
            width=self.ui.text.width(call.args[2],9,index==0)
            self.assertAlmostEqual(call.args[1][0]+width/2,index*58+29)
        self.assertEqual(frame.getpixel((4,10)),tuple(bytes.fromhex(SELECT[1:])))

    def test_battery_fill_and_chat_cache_track_live_charge_without_sysfs_reads(self):
        self.ui.open_chat(self.store.chats()[0]);self.ui.battery=25
        first=self.ui.render();first_key=self.ui.render_key()
        self.ui.battery=100;second=self.ui.render()
        self.assertNotEqual(first_key,self.ui.render_key())
        def count(frame):
            color=tuple(bytes.fromhex(TEXT[1:]))
            return sum(frame.getpixel((x,y))==color for x in range(298,314) for y in range(7,14))
        self.assertGreater(count(second),count(first))
        self.ui.battery=None;self.assertEqual(count(self.ui.render()),0)
        with patch('meshcore_zero.battery.read_capacity',side_effect=AssertionError('Rendering must not poll hardware')):
            with patch.object(self.ui.text,'draw',wraps=self.ui.text.draw) as draw:
                self.ui._chat_cache_key=None;self.ui.render()
            values=[c.args[2] for c in draw.call_args_list]
            self.assertFalse(any('Grey:' in s or 'no echo' in s or '%' in s for s in values))
