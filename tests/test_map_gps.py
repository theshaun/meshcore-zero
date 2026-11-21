import asyncio
import json
import math
import os
from pathlib import Path
import pty
import select
import sys
import tempfile
import termios
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor'))
from meshcore_zero.gps import NMEA,Fix,SerialInput,LocationPrivacyMixin,port_available
from meshcore_zero.map_ui import position,manual_position,distance_bearing,has_position,MapUI,SCALES
from meshcore_zero.ui import UI
from meshcore_zero.store import Store
from meshcore_zero.radio import Backend
from openhop_core import CompanionRadio,LocalIdentity
from openhop_core.companion.models import Contact
from openhop_core.protocol import Packet
from openhop_core.protocol.packet_builder import PacketBuilder
SEED=bytes(range(32))

def sentence(body):
    checksum=0
    for c in body:checksum^=ord(c)
    return f'${body}*{checksum:02X}\r\n'

class GPSTests(unittest.TestCase):
    def test_checksum_coordinates_fix_loss_and_expiry(self):
        gps=NMEA()
        good=sentence('GNGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,')
        self.assertTrue(gps.feed(good,100));self.assertAlmostEqual(gps.fix.latitude,48.1173);self.assertAlmostEqual(gps.fix.longitude,11.5166667)
        self.assertEqual(gps.satellites,8);self.assertIsNotNone(gps.fresh(115));self.assertIsNone(gps.fresh(116))
        old=gps.fix
        for invalid in (good.replace('*','*00'),good.replace('4807','4867'),'$GNGGA,bad*00','\xff'*300):
            self.assertFalse(gps.feed(invalid,101));self.assertEqual(gps.fix,old)
        self.assertTrue(gps.feed(sentence('GNGGA,123520,,,,,0,03,9.9,,,,,,'),102));self.assertIsNone(gps.fix);self.assertEqual(gps.last_fix,old)
        self.assertTrue(gps.feed(sentence('GPRMC,123519,A,3450.000,S,05822.000,W,0,0,230394,,,A'),103))
        self.assertAlmostEqual(gps.fix.latitude,-(34+50/60));self.assertAlmostEqual(gps.fix.longitude,-(58+22/60))
        gps.feed(sentence('GPRMC,123519,V,,,,,,,230394,,,N'),104);self.assertIsNone(gps.fix)
        self.assertTrue(gps.feed(sentence('GNGGA,123519,0000.000,N,00000.000,E,1,08,0.9,0,M,0,M,,'),105))
        self.assertEqual((gps.fix.latitude,gps.fix.longitude),(0,0))
        gps.feed(sentence('GPRMC,123519,A,4807.038,N,01131.000,E,0,0,230394,,,E'),106)
        self.assertIsNone(gps.fix)

    def test_uart_restores_configuration_and_only_reads_input(self):
        master,slave=pty.openpty()
        try:
            before=termios.tcgetattr(slave);reader=SerialInput(os.ttyname(slave))
            try:
                wire=sentence('GNRMC,123519,A,4807.038,N,01131.000,E,0,0,230394,,,A').encode()
                os.write(master,wire);self.assertTrue(select.select([reader.fd],[],[],1)[0])
                self.assertEqual(reader.read(),[wire.rstrip(b'\n')])
            finally:reader.close()
            after=termios.tcgetattr(slave)
            # BSD may set transient PENDIN when canonical input is restored.
            after[3]&=~getattr(termios,'PENDIN',0);before[3]&=~getattr(termios,'PENDIN',0)
            self.assertEqual(after,before)
        finally:os.close(master);os.close(slave)

class MapTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);self.addCleanup(self.store.db.close);self.ui=UI(self.store)
    def add_node(self,key='ab'*32,lat=55.96,lon=-3.18,age=0):
        data={'public_key':key,'name':'Relay 🏴','adv_type':2,'gps_lat':lat,'gps_lon':lon,'last_advert_timestamp':time.time()-age}
        with self.store.db:self.store.db.execute('INSERT OR REPLACE INTO nodes VALUES (?,?)',(key,json.dumps(data)))
        return data
    def test_geometry_and_missing_or_invalid_locations(self):
        d,b=distance_bearing((0,0),(1,0));self.assertAlmostEqual(d,111195,delta=10);self.assertAlmostEqual(b,0)
        self.assertAlmostEqual(distance_bearing((0,0),(0,1))[1],90)
        self.assertLess(distance_bearing((0,179.9),(0,-179.9))[0],23000)
        self.assertIsNone(position(float('nan'),0));self.assertIsNone(position(91,0));self.assertIsNone(position(True,2))
        self.assertEqual(manual_position('55.95, -3.19'),(55.95,-3.19))
        with self.assertRaises(ValueError):manual_position('55.95')
        self.assertIsNone(has_position({'gps_lat':0,'gps_lon':0}))
        engine=CompanionRadio(None,LocalIdentity(SEED));engine.prefs.advert_loc_policy=1
        packet=PacketBuilder.create_advert(LocalIdentity(SEED),name='Origin',lat=0,lon=0,flags=0x11)
        self.assertEqual(has_position({'gps_lat':0,'gps_lon':0,'last_advert_packet':packet.write_to().hex()}),(0,0))

    async def test_no_fix_manual_fallback_zoom_selection_details_and_auto(self):
        u=self.ui;u.switch_tab(3);self.assertEqual(u.screen,'map');self.assertIsNone(u.map_ui.centre()[0]);u.render()
        self.add_node(age=90000);self.add_node(key='cd'*32,lat=55.97,lon=-3.17)
        await u.key('m')
        for char in '55.95,-3.19':await u.key(char)
        await u.key('enter');self.assertEqual(u.map_ui.centre()[1],'Manual')
        _,_,dots,scale=u.map_ui.model();self.assertEqual(len(dots),2);self.assertTrue(dots[0]['stale'])
        u.render();old=u.map_ui.selected_key;await u.key('right');self.assertNotEqual(u.map_ui.selected_key,old)
        await u.key('up');self.assertIsNotNone(u.map_ui.zoom);await u.key('0');self.assertIsNone(u.map_ui.zoom)
        await u.key('enter');self.assertEqual(u.screen,'map_details');u.render()
        await u.key('escape');self.assertEqual(u.screen,'map')
        await u.key('tab');self.assertEqual(u.screen,'settings')
        # A current fix takes priority; a lost old fix falls back to manual.
        u.gps.parser.feed(sentence('GNGGA,123519,4807.038,N,01131.000,E,1,08,0.9,0,M,0,M,,'))
        self.assertEqual(u.map_ui.centre()[1],'GPS fix')
        u.gps.parser.fix=None;self.assertEqual(u.map_ui.centre()[1],'Last GPS')
        u.gps.parser.last_fix=Fix(1,2,time.monotonic()-301);self.assertEqual(u.map_ui.centre()[1],'Manual')

    async def test_sharing_is_opt_in_cancel_first_and_manual_position_never_advertised(self):
        u=self.ui;backend=Backend(self.store);backend.engine=CompanionRadio(None,LocalIdentity(SEED));backend.gps=u.gps;u.backend=backend
        u.gps.parser.feed(sentence('GNGGA,123519,4807.038,N,01131.000,E,1,08,0.9,0,M,0,M,,'))
        backend.update_location_policy();self.assertEqual(backend.engine.prefs.advert_loc_policy,0)
        u.screen='settings';u.selected=8;await u.key('enter');self.assertEqual(u.screen,'gps_sharing');self.assertEqual(u.map_ui.share_choice,1)
        u.render();await u.key('enter');self.assertEqual(self.store.get('gps_broadcast','off'),'off')
        await u.key('enter');await u.key('tab');await u.key('enter');self.assertEqual(self.store.get('gps_broadcast'),'on')
        self.assertEqual(backend.engine.prefs.advert_loc_policy,1)
        backend.engine._send_packet=AsyncMock(return_value=True)
        await backend.engine.advertise();packet=backend.engine._send_packet.await_args.args[0]
        self.assertTrue(packet.get_payload()[100]&0x10);self.assertTrue(backend.location_packet_allowed(packet.write_to()))
        await u.key('enter');self.assertEqual(self.store.get('gps_broadcast'),'off');self.assertEqual(backend.engine.prefs.latitude,0)
        self.assertFalse(backend.location_packet_allowed(packet.write_to()))
        await backend.engine.advertise();self.assertFalse(backend.engine._send_packet.await_args.args[0].get_payload()[100]&0x10)
        self.store.set('gps_broadcast','on');self.store.set('map_position','55.95,-3.19');u.gps.parser.fix=None
        backend.update_location_policy();self.assertEqual(backend.engine.prefs.advert_loc_policy,0)
        # Incoming/replayed adverts from other nodes are not treated as our location.
        foreign=PacketBuilder.create_advert(LocalIdentity(bytes(range(32,64))),name='Other',lat=1,lon=2)
        self.assertTrue(backend.location_packet_allowed(foreign.write_to()))

    async def test_location_service_waits_for_startup_then_limits_broadcasts(self):
        u=self.ui;backend=Backend(self.store);backend.engine=CompanionRadio(None,LocalIdentity(SEED));backend.engine._running=True
        backend.gps=u.gps;u.backend=backend;self.store.set('gps_broadcast','on')
        clock=[1000];ticks=iter((1001,1100,1200,1999,2000,2001))
        class Port:
            def read(self):return [sentence('GNGGA,123519,4807.038,N,01131.000,E,1,08,0.9,0,M,0,M,,')]
            def close(self):pass
        u.gps.serial=Port()
        sent=[]
        async def announce(**kwargs):sent.append(clock[0]);u.gps.last_broadcast=clock[0];return True
        backend.announce=AsyncMock(side_effect=announce)
        async def tick(_):
            try:clock[0]=next(ticks)
            except StopIteration:u.running=False
        with patch('meshcore_zero.gps.time',SimpleNamespace(monotonic=lambda:clock[0])),patch('meshcore_zero.gps.asyncio.sleep',side_effect=tick):
            await u.gps.run(SimpleNamespace(done=lambda:clock[0]>=1001))
        self.assertEqual(sent,[1001,1999])
        self.assertTrue(all(call.kwargs=={'notify':False} for call in backend.announce.await_args_list))

    async def test_advert_metadata_survives_contact_persistence_and_only_accepts_verified_callback(self):
        u=self.ui;backend=Backend(self.store);backend.engine=CompanionRadio(None,LocalIdentity(SEED))
        peer=LocalIdentity(bytes(range(32,64)));packet=PacketBuilder.create_advert(peer,name='Peer',lat=55.96,lon=-3.18)
        contact=Contact(public_key=peer.get_public_key(),name='Peer',adv_type=1,gps_lat=55.96,gps_lon=-3.18,last_advert_packet=packet.write_to(),last_advert_timestamp=int(time.time()))
        backend.engine.contacts.add(contact);backend.radio_received(packet.write_to(),-85,6.25)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM nodes').fetchone()[0],0)
        await backend.advert(contact);backend.persist_contacts()
        data=json.loads(self.store.db.execute('SELECT data FROM nodes').fetchone()[0])
        self.assertEqual(data['map_rssi'],-85);self.assertEqual(data['map_snr'],6.25);self.assertGreater(data['map_position_at'],0)

class PrivacyTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabling_sharing_while_advert_is_queued_cancels_before_set_tx(self):
        ready=asyncio.Event();release=asyncio.Event();sent=[]
        class Driver:
            async def send(self,data):ready.set();await release.wait();return await self._execute_transmission()
            async def _execute_transmission(self):sent.append(True);return True
        class Radio(LocationPrivacyMixin,Driver):pass
        r=Radio();allowed=True;r.location_allowed=lambda _:allowed
        task=asyncio.create_task(r.send(b'fixture'));await ready.wait();allowed=False;release.set()
        with self.assertRaisesRegex(RuntimeError,'sharing off'):await task
        self.assertFalse(sent)
    async def test_console_and_active_services_are_not_opened(self):
        with patch('meshcore_zero.gps.Path.read_text',return_value='console=ttyS0,115200'),patch('meshcore_zero.gps.asyncio.create_subprocess_exec') as create:
            self.assertFalse(await port_available());create.assert_not_called()
        proc=SimpleNamespace(communicate=AsyncMock(return_value=(b'inactive\nactive\ninactive\n',b'')))
        with patch('meshcore_zero.gps.Path.read_text',return_value='console=tty1'),patch('meshcore_zero.gps.asyncio.create_subprocess_exec',AsyncMock(return_value=proc)):
            self.assertFalse(await port_available())
