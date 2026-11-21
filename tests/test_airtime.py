import asyncio
from contextlib import closing
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor'))
from meshcore_zero.airtime import AirtimeBudget
from meshcore_zero.regional_radio import RegionalRadioMixin
from meshcore_zero.regions import PRESETS


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'airtime.sqlite';self.now=10000
        self.budget=AirtimeBudget(self.path,clock=lambda:self.now)

    def test_bursts_exhaustion_restart_and_rolling_expiry(self):
        for _ in range(6):self.budget.reserve(1)
        self.budget.reserve(354)
        reopened=AirtimeBudget(self.path,clock=lambda:self.now)
        with self.assertRaisesRegex(ValueError,'Hourly'):reopened.reserve(.001)
        self.now+=3600
        with self.assertRaises(ValueError):reopened.reserve(1)  # Packet ends still overlap.
        self.now+=1
        reopened.reserve(6)  # Six early packets expire, large later packet stays.
        with self.assertRaises(ValueError):reopened.reserve(.01)
        self.now+=354
        reopened.reserve(354)

    def test_failed_reservations_and_clock_rollback_cannot_reset_usage(self):
        self.budget.reserve(359)
        for bad in (0,-1,float('nan'),float('inf'),2):
            with self.assertRaises(ValueError):self.budget.reserve(bad)
        self.now-=1
        with self.assertRaisesRegex(ValueError,'clock'):self.budget.reserve(.1)
        self.now+=1
        self.budget.reserve(1)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT SUM(seconds) FROM tx').fetchone()[0],360)
        self.assertEqual(self.path.stat().st_mode & 0o777,0o600)

    def test_independent_writers_cannot_overspend(self):
        from concurrent.futures import ThreadPoolExecutor
        def reserve(_):
            other=AirtimeBudget(self.path,clock=lambda:10000)
            try:other.reserve(10);return True
            except ValueError:return False
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sum(pool.map(reserve,range(40))),36)


class PhysicalTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_packet_lengths_every_tx_and_failures_are_accounted(self):
        with tempfile.TemporaryDirectory() as tmp:
            budget=AirtimeBudget(Path(tmp)/'airtime.sqlite',clock=lambda:10000)
            class Driver:
                def __init__(self,**cfg):self.__dict__.update(cfg);self.preamble_length=16;self.sent=[];self.fail=False
                async def send(self,data):return await self._execute_transmission(data)
                async def _execute_transmission(self,data):
                    self.sent.append(data)
                    if self.fail:raise RuntimeError('uncertain TX')
                    return {'ok':True}
            class Radio(RegionalRadioMixin,Driver):pass
            radio=Radio(region='SCO',airtime_budget=budget,**PRESETS['SCO'])
            await asyncio.gather(*(radio.send(b'a'*n) for n in (15,30,60,90,15,30)))
            self.assertEqual(len(radio.sent),6)
            radio.fail=True
            with self.assertRaises(RuntimeError):await radio.send(b'ack')
            with closing(sqlite3.connect(budget.path)) as db:
                entries=db.execute('SELECT seconds FROM tx').fetchall()
            self.assertEqual(len(entries),7)
            self.assertLess(entries[0][0],entries[2][0])
            budget.reserve(359-sum(v[0] for v in entries))
            with self.assertRaisesRegex(ValueError,'Hourly'):await radio.send(b'x'*200)
            self.assertEqual(len(radio.sent),7)
            # Other regions do not inherit an artificial European budget.
            us=Radio(region='US',airtime_budget=budget,**PRESETS['US'])
            await us.send(b'x'*200)
            self.assertEqual(len(us.sent),1)

    async def test_exhausted_budget_releases_rx_buffer_after_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            budget=AirtimeBudget(Path(tmp)/'airtime.sqlite',clock=lambda:10000)
            budget.reserve(360)
            class Driver:
                def __init__(self,**cfg):self.__dict__.update(cfg);self.preamble_length=16;self.rx_ready=False
                async def send(self,data):
                    self._tx_buffer_busy=True
                    try:return await self._execute_transmission(0)
                    finally:await self._restore_rx_mode()
                async def _execute_transmission(self,_):raise AssertionError('SetTx must not run')
                async def _restore_rx_mode(self):self.rx_ready=not self._tx_buffer_busy
            class Radio(RegionalRadioMixin,Driver):pass
            radio=Radio(region='SCO',airtime_budget=budget,**PRESETS['SCO'])
            with self.assertRaisesRegex(ValueError,'Hourly'):await radio.send(b'ack')
            self.assertTrue(radio.rx_ready)
            self.assertFalse(radio._tx_buffer_busy)


class ConversationTests(unittest.IsolatedAsyncioTestCase):
    async def test_back_to_back_messages_and_advert_have_no_app_pause(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        from meshcore_zero.radio import Backend
        from meshcore_zero.store import Store
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp)
            try:
                store.join('#testing')
                backend=Backend(store);backend.region='SCO';backend.channels={'#testing':1}
                backend.engine=SimpleNamespace(is_running=True,prefs=SimpleNamespace(node_name='Test'),
                    send_channel_message=AsyncMock(return_value=True),advertise=AsyncMock(return_value=True))
                chat=dict(store.db.execute("SELECT * FROM chats WHERE id='#testing'").fetchone())
                for n in range(6):await backend.send(chat,str(n))
                await backend.announce()
                await backend.send(chat,'after advert')
                self.assertEqual(backend.engine.send_channel_message.await_count,7)
                self.assertEqual([r['status'] for r in store.history('#testing')],['sent']*7)
            finally:store.db.close()
