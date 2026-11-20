import asyncio
import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
from meshcore_zero.store import Store
from meshcore_zero.ui import UI
from meshcore_zero.repeater import request_status,repeater_clock,status_lines,battery_estimate
from meshcore_zero.startup_advert import announce_after_checks

KEY='ab'*32
class RepeaterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);self.addCleanup(self.store.db.close)
        with self.store.db:self.store.db.execute('INSERT INTO nodes VALUES(?,?)',(KEY,json.dumps(dict(public_key=KEY,name='Test repeater',adv_type=2))))
        self.ui=UI(self.store)

    async def test_confirmation_password_mask_cancel_and_retry(self):
        self.ui.screen='nodes';await self.ui.key('enter')
        self.assertEqual(self.ui.screen,'repeater');self.assertEqual(self.ui.repeater_state,'confirm')
        self.assertEqual(self.ui.active_tab(),2);self.assertEqual(self.ui.render().size,(320,170))
        await self.ui.key('tab');await self.ui.key('enter');self.assertEqual(self.ui.screen,'nodes')
        await self.ui.key('enter');await self.ui.key('enter')
        for c in 'secret':await self.ui.key(c)
        with patch.object(self.ui.text,'draw',wraps=self.ui.text.draw) as draw:self.ui.render()
        self.assertFalse(any('secret' in str(c) for c in draw.call_args_list))
        with patch('meshcore_zero.repeater.request_status',new=AsyncMock(return_value=({'batt_milli_volts':3900},1700000000))) as request:
            self.ui.backend=object();await self.ui.key('enter');self.assertEqual(self.ui.repeater_state,'save');self.assertEqual(self.ui.repeater_choice,1);await self.ui.key('enter');await self.ui.repeater_task
        request.assert_awaited_once_with(self.ui.backend,KEY,'secret')
        self.assertEqual(self.ui.repeater_state,'result');self.assertEqual(self.ui.repeater_password,'')
        self.assertFalse(any('secret' in str(tuple(row)) for row in self.store.db.execute('SELECT * FROM settings')))
        self.assertEqual(self.ui.render().size,(320,170));await self.ui.key('escape');self.assertEqual(self.ui.screen,'nodes')

    async def test_login_failure_never_requests_status(self):
        engine=SimpleNamespace(is_running=True,send_login=AsyncMock(return_value={'success':False}),send_status_request=AsyncMock())
        backend=SimpleNamespace(engine=engine,send_lock=asyncio.Lock(),next_tx=0,region='US')
        with self.assertRaisesRegex(ValueError,'Login failed'):await request_status(backend,KEY,'wrong')
        engine.send_status_request.assert_not_awaited()

    async def test_status_and_clock_only_after_successful_login(self):
        engine=SimpleNamespace(is_running=True,send_login=AsyncMock(return_value={'success':True}),send_status_request=AsyncMock(return_value={'success':True,'stats':{'last_snr':2.25}}))
        backend=SimpleNamespace(engine=engine,send_lock=asyncio.Lock(),next_tx=0,region='US')
        with patch('meshcore_zero.repeater.repeater_clock',new=AsyncMock(return_value=1700000000)):
            stats,clock=await request_status(backend,KEY,'password')
        self.assertEqual(stats['last_snr'],2.25);self.assertEqual(clock,1700000000)
        engine.send_status_request.assert_awaited_once_with(bytes.fromhex(KEY),timeout=20)

    async def test_clock_matches_tag_even_when_reply_arrives_during_send(self):
        callbacks=[]
        async def send(key,data,timeout_seconds):
            callbacks[0]((42).to_bytes(4,'little'),b'',{'type':'basic','clock':1700000000})
            return SimpleNamespace(success=True,expected_ack=42)
        engine=SimpleNamespace(on_binary_response=callbacks.append,send_anon_req=send,remove_push_callback=lambda _,cb:callbacks.remove(cb))
        self.assertEqual(await repeater_clock(engine,bytes.fromhex(KEY)),1700000000);self.assertEqual(callbacks,[])

    def test_display_uses_reported_fields_and_explicit_estimate(self):
        lines=dict(status_lines({'batt_milli_volts':3900,'total_up_time_secs':90061,'noise_floor':-115,'last_snr':-2.25},1700000000))
        self.assertIn('~75%',lines['Battery*']);self.assertEqual(lines['Uptime'],'1d 1h 1m')
        self.assertEqual(lines['Noise floor'],'-115 dBm');self.assertEqual(lines['Last SNR'],'-2.25 dB')
        self.assertIn('UTC',lines['Clock']);self.assertIsNone(battery_estimate(12000))
        self.assertEqual(dict(status_lines({}))['Clock'],'Unavailable')

class AdvertTests(unittest.IsolatedAsyncioTestCase):
    async def test_waits_for_checks_and_update_decision_then_announces_once(self):
        ui=SimpleNamespace(running=True,startup_release=('new',),screen='inbox',launch_state='',notice=lambda _:None)
        backend=SimpleNamespace(engine=SimpleNamespace(is_running=True),announce=AsyncMock())
        ready=asyncio.Event()
        task=asyncio.create_task(announce_after_checks(ui,backend,ready.wait(),asyncio.sleep(0)))
        await asyncio.sleep(0);backend.announce.assert_not_awaited();ready.set()
        await asyncio.sleep(.01);backend.announce.assert_not_awaited()
        ui.startup_release=None;await task;backend.announce.assert_awaited_once()

    async def test_offline_radio_or_exit_sends_nothing(self):
        for running,engine in [(False,SimpleNamespace(is_running=True)),(True,None)]:
            ui=SimpleNamespace(running=running,startup_release=None,screen='inbox',launch_state='')
            backend=SimpleNamespace(engine=engine,announce=AsyncMock())
            await announce_after_checks(ui,backend,asyncio.sleep(0),asyncio.sleep(0));backend.announce.assert_not_awaited()
