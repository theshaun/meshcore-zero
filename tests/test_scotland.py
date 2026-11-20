"""ScotMesh preset and firmware wire-format checks; no physical transmissions."""
import asyncio
import hashlib
import hmac
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor'))
from openhop_core import CompanionRadio,LocalIdentity
from openhop_core.protocol import Packet
from meshcore_zero.regions import PRESETS,EUROPE,configure_protocol
from meshcore_zero.store import Store,radio_config
from meshcore_zero.ui import UI

class ScotlandTests(unittest.IsolatedAsyncioTestCase):
    async def test_selected_only_on_confirmation_and_preserves_existing_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Store(tmp);s.set('identity','fixture');s.set('coding_rate_US',8)
            s.join('#testing');s.add('#testing','Fixture','Keep history')
            ui=UI(s);ui.screen='regions';ui.selected=list(PRESETS).index('SCO')
            self.assertEqual(ui.render().size,(320,170));await ui.key('escape')
            self.assertEqual(s.get('region','US'),'US')
            ui.screen='regions';ui.selected=list(PRESETS).index('SCO');await ui.key('enter')
            self.assertEqual(s.get('region'),'SCO');self.assertEqual(s.get('identity'),'fixture')
            self.assertEqual(len(s.history('#testing')),1);self.assertEqual(radio_config(s,'US')['coding_rate'],8)
            self.assertEqual(radio_config(s),PRESETS['UK']);self.assertIn('SCO',EUROPE)
            s.db.close()

    async def test_real_message_and_advert_builders_encode_scope_and_three_byte_paths(self):
        engine=CompanionRadio(None,LocalIdentity(bytes(range(32))),node_name='Fixture')
        configure_protocol(engine,'SCO')
        key=hashlib.sha256(b'#sco').digest()[:16]
        self.assertEqual(engine.get_default_flood_scope(),('sco',key))
        engine.set_channel(0,'#testing',hashlib.sha256(b'#testing').digest()[:16])
        engine._send_packet=AsyncMock(return_value=True)
        self.assertTrue(await engine.send_channel_message(0,'Offline fixture'))
        self.assertTrue(await engine.advertise(flood=True))
        for call in engine._send_packet.await_args_list:
            pkt=Packet();self.assertTrue(pkt.read_from(call.args[0].write_to()))
            self.assertEqual(pkt.get_route_type(),0) # firmware TRANSPORT_FLOOD
            self.assertEqual(pkt.get_path_hash_size(),3)
            expected=struct.unpack('<H',hmac.new(key,bytes([pkt.get_payload_type()])+pkt.get_payload(),hashlib.sha256).digest()[:2])[0]
            expected=1 if expected==0 else 65534 if expected==65535 else expected
            self.assertEqual(pkt.transport_codes[0],expected);self.assertEqual(pkt.transport_codes[1],0)
        # Switching profiles clears the default scope rather than leaking sco.
        configure_protocol(engine,'UK');self.assertIsNone(engine.get_default_flood_scope())
        engine._send_packet.reset_mock();await engine.advertise(flood=True)
        pkt=engine._send_packet.await_args.args[0]
        self.assertEqual(pkt.get_route_type(),1);self.assertEqual(pkt.get_path_hash_size(),1)
        configure_protocol(engine,'SCO');engine._send_packet.reset_mock()
        await engine.advertise(flood=False)
        self.assertEqual(engine._send_packet.await_args.args[0].get_route_type(),2)
