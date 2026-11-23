import asyncio
import errno
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from meshcore_zero.cap import CapPower
from meshcore_zero.regions import PRESETS, PATH_BYTES, EUROPE
from meshcore_zero.store import Store, radio_config
from meshcore_zero.ui import UI
from meshcore_zero.regional_radio import RegionalRadioMixin, wait_clear

class RegionTests(unittest.TestCase):
    def test_picker_preserves_identity_and_regional_overrides(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                s=Store(tmp);s.set('identity','synthetic-identity');s.set('coding_rate_US',8)
                s.join('#testing');s.add('#testing','Peer','Saved history')
                ui=UI(s);ui.screen='settings';ui.selected=0
                await ui.key('enter');self.assertEqual(ui.screen,'regions')
                await ui.key('down');await ui.key('down');await ui.key('enter')
                self.assertEqual(s.get('region'),'JP');self.assertEqual(s.get('identity'),'synthetic-identity')
                self.assertEqual(radio_config(s)['tx_power'],13)
                self.assertEqual(radio_config(s,'US')['coding_rate'],8)
                self.assertEqual(len(s.history('#testing')),1)
                ui.screen='regions';ui.selected=12
                self.assertEqual(ui.render().size,(320,170))
                await ui.key('escape');self.assertEqual(s.get('region'),'JP')
                s.db.close()
        asyncio.run(scenario())

    def test_slovakia_profile_matches_community_and_preserves_other_profiles(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                s=Store(tmp);s.set('coding_rate_US',8);s.set('identity','synthetic-identity')
                before=radio_config(s,'US')
                ui=UI(s);ui.screen='regions';ui.selected=list(PRESETS).index('SK')
                self.assertEqual(ui.render().size,(320,170))
                await ui.key('enter')
                self.assertEqual(s.get('region'),'SK')
                self.assertEqual(radio_config(s),dict(frequency=869618000,bandwidth=62500,spreading_factor=7,coding_rate=5,tx_power=14))
                self.assertEqual(PATH_BYTES['SK'],2);self.assertIn('SK',EUROPE)
                self.assertEqual(radio_config(s,'US'),before)
                self.assertEqual(s.get('identity'),'synthetic-identity')
                s.set('coding_rate_SK',8)
                s.db.close();s=Store(tmp)
                self.assertEqual(radio_config(s)['coding_rate'],8)
                self.assertEqual(radio_config(s,'US')['coding_rate'],8)
                s.db.close()
        asyncio.run(scenario())

    def test_available_presets_match_cap_band_and_invalid_region_is_rejected(self):
        from meshcore_zero.preset_catalog import catalog,supported
        with tempfile.TemporaryDirectory() as tmp:
            s=Store(tmp)
            try:
                for region,entry in catalog(s).items():
                    if supported(entry):
                        cfg=radio_config(s,region)
                        self.assertTrue(868000000<=cfg['frequency']<=923000000)
                        self.assertIn(cfg['coding_rate'],(5,6,7,8))
                    else:
                        with self.assertRaisesRegex(ValueError,'different radio CAP'):radio_config(s,region)
                self.assertEqual(PATH_BYTES['CA'],3);self.assertEqual(PATH_BYTES['AU'],2)
                s.set('region','INVALID')
                with self.assertRaises(ValueError):radio_config(s)
            finally:s.db.close()

class CapTests(unittest.TestCase):
    def exercise(self, mode):
        root=Path(self.tmp.name)
        for name,value in [('ext_5v_out','0'),('grove_5v_out','1')]:
            (root/name).mkdir(exist_ok=True);(root/name/'brightness').write_text(value)
        bus=MagicMock()
        class FakeCap(CapPower):
            def __init__(inner):
                super().__init__();inner.regs={1:0xa2,3:0xaa,5:0x54,7:0xff,11:0xf3};inner.writes=[]
            def read(inner,reg):
                if mode=='legacy':raise OSError(getattr(errno,'EREMOTEIO',121),'NACK')
                if mode=='permission':raise PermissionError(errno.EACCES,'denied')
                return 0 if mode=='unknown' and reg==1 else inner.regs[reg]
            def write(inner,reg,value):
                if mode=='broken':raise OSError(errno.EIO,'write failed')
                inner.writes.append((reg,value));inner.regs[reg]=value
        cap=FakeCap()
        self.patches=[patch('meshcore_zero.cap.Path',return_value=root),patch('meshcore_zero.cap.time.sleep'),
                      patch.dict(sys.modules,{'periphery':SimpleNamespace(I2C=lambda path:bus)})]
        for p in self.patches:p.start();self.addCleanup(p.stop)
        return cap,bus

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def chip(self, signature=b'SX1262 Rev'):
        return SimpleNamespace(readRegister=lambda address,length:signature)

    def test_new_cap_enables_switch_and_restores_only_its_pin(self):
        cap,bus=self.exercise('new');cap.start()
        self.assertEqual(cap.confirm_radio(self.chip()),'CAP LoRa-1262')
        self.assertEqual(cap.writes[0],(5,0x55))
        self.assertEqual(cap.regs[3]&1,1);self.assertEqual(cap.regs[7]&1,0);self.assertEqual(cap.regs[11]&1,0)
        cap.regs[5]|=0x80;cap.close()
        self.assertEqual(cap.regs[5],0xd4)
        self.assertEqual(cap.regs[3],0xaa);self.assertEqual(cap.regs[7],0xff);self.assertEqual(cap.regs[11],0xf3)
        self.assertEqual((Path(self.tmp.name)/'ext_5v_out/brightness').read_text(),'0')
        cap.close();bus.close.assert_called_once()

    def test_legacy_requires_real_spi_signature_and_never_writes_expander(self):
        cap,bus=self.exercise('legacy');cap.start()
        with self.assertRaises(RuntimeError):cap.confirm_radio(self.chip(bytes(16)))
        self.assertEqual(cap.confirm_radio(self.chip()),'Legacy CAP LoRa868')
        self.assertEqual(cap.writes,[]);cap.close();bus.close.assert_called_once()

    def test_bus_permissions_and_unrecognized_devices_do_not_become_legacy(self):
        cap,bus=self.exercise('permission')
        with self.assertRaises(PermissionError):cap.start()
        self.assertEqual(cap.writes,[])

    def test_unrecognized_expander_is_never_written(self):
        cap,bus=self.exercise('unknown')
        with self.assertRaises(RuntimeError):cap.start()
        self.assertEqual(cap.writes,[])

class JapanTests(unittest.IsolatedAsyncioTestCase):
    async def test_energy_sensing_requires_a_clear_window_and_fails_closed(self):
        samples=[]
        def clear():samples.append(1);return -100
        await wait_clear(clear,duration=.005,timeout=.1)
        self.assertGreaterEqual(len(samples),3)
        with self.assertRaises(RuntimeError):await wait_clear(lambda:-50,timeout=.01)
        with self.assertRaises(RuntimeError):await wait_clear(lambda:None,timeout=.01)
        with self.assertRaises(RuntimeError):await wait_clear(clear,lambda:True,timeout=.01)

    def radio(self,region='JP'):
        class Driver:
            def __init__(inner,**cfg):
                inner.__dict__.update(cfg);inner.preamble_length=16;inner.transmitted=0
                inner._tx_done_event=asyncio.Event();inner._rx_done_event=asyncio.Event()
                inner.lora=MagicMock();inner.lora.busyCheck.return_value=False;inner.lora.getRssiInst.return_value=200
            def _calculate_tx_timeout(inner,length):return (1000,64000)
            async def _prepare_radio_for_tx(inner):return True,[]
            async def _drain_pending_rx_irq_before_buffer_reuse(inner):pass
            def _control_tx_rx_pins(inner,**kwargs):pass
            def _get_rx_irq_mask(inner):return 1
            def is_receiving_packet(inner):return False
            async def send(inner,data):
                inner._calculate_tx_timeout(len(data))
                await inner._prepare_radio_for_tx();inner.transmitted+=1;return {}
        class Radio(RegionalRadioMixin,Driver):pass
        return Radio(region=region,**PRESETS[region])

    async def test_all_physical_sends_enforce_airtime_power_lbt_and_spacing(self):
        r=self.radio()
        with self.assertRaises(ValueError):await r.send(b'x'*200)
        self.assertEqual(r.transmitted,0)
        with patch('meshcore_zero.regional_radio.wait_clear',new=AsyncMock(side_effect=RuntimeError('busy'))):
            with self.assertRaises(RuntimeError):await r.send(b'x'*12)
        self.assertEqual(r.transmitted,0)
        await r.send(b'x'*12);first=r._last_regional_tx
        await r.send(b'x'*12)
        self.assertGreaterEqual(r._last_regional_tx-first,.05)
        self.assertEqual(r.transmitted,2)
        r.tx_power=20
        with self.assertRaises(RuntimeError):await r.send(b'x')
        self.assertEqual(r.transmitted,2)
        # Normal US TX is unaffected by Japan's stricter path.
        normal=self.radio('US');await normal.send(b'x'*200);self.assertEqual(normal.transmitted,1)
