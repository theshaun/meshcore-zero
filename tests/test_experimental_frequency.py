"""Experimental preset consent is explicit, bounded and retained offline. No RF."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor'))
from meshcore_zero import backup
from meshcore_zero.store import Store,radio_config
from meshcore_zero.ui import UI
from meshcore_zero import preset_catalog as pc


class ExperimentalTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);self.addCleanup(self.store.db.close)
        self.store.set('identity',bytes(range(32)).hex())
        self.ui=UI(self.store)
        self.engine=MagicMock()
        self.ui.backend=SimpleNamespace(engine=self.engine,state='Ready',error='')
        self.entry=pc.catalog(self.store)['US_SOCAL']

    def open_picker(self):
        self.ui.screen='regions';self.ui.region_catalog=None
        self.ui.selected=list(self.ui.region_choices()).index('US_SOCAL')

    async def test_cancel_is_default_enter_and_escape_preserve_radio_identity_and_history(self):
        s=self.store;s.join('#testing');s.add('#testing','Fixture','Keep this')
        before=radio_config(s);identity=s.get('identity')
        self.open_picker();revision=self.ui.render_key();await self.ui.key('enter')
        self.assertIsNotNone(self.ui.experimental_entry);self.assertEqual(self.ui.experimental_choice,0)
        self.assertNotEqual(self.ui.render_key(),revision)
        self.assertEqual(self.ui.render().size,(320,170));self.assertEqual(self.ui.active_tab(),4)
        await self.ui.key('enter')  # Default Cancel must never accept.
        self.assertIsNone(self.ui.experimental_entry);self.assertIsNone(s.get(pc.ACK_PREFIX+'US_SOCAL'))
        await self.ui.key('enter');await self.ui.key('right');await self.ui.key('escape')
        self.assertEqual(radio_config(s),before);self.assertEqual(s.get('identity'),identity)
        self.assertEqual(len(s.history('#testing')),1);self.assertEqual(self.engine.mock_calls,[])

    async def test_explicit_acceptance_persists_but_changed_rf_parameters_require_new_consent(self):
        s=self.store
        with self.assertRaises(ValueError):pc.select_profile(s,self.entry)
        with self.assertRaises(ValueError):radio_config(s,'US_SOCAL')
        self.open_picker();await self.ui.key('enter');await self.ui.key('tab');await self.ui.key('enter')
        self.assertEqual(s.get('region'),'US_SOCAL');self.assertEqual(self.ui.screen,'settings')
        self.assertTrue(pc.accepted(s,self.entry));self.assertEqual(radio_config(s)['frequency'],927875000)
        self.assertEqual(self.engine.mock_calls,[])  # Saving never retunes/transmits.
        other=Store(self.tmp.name)
        try:self.assertEqual(radio_config(other)['frequency'],927875000)
        finally:other.db.close()
        self.open_picker();await self.ui.key('enter')
        self.assertIsNone(self.ui.experimental_entry)  # Remember this preset.
        changed=copy.deepcopy(self.entry);changed['radio']['frequency']=927800000
        self.ui.screen='regions';self.ui.region_catalog=pc.catalog(s)
        self.ui.region_catalog['US_SOCAL']=changed;self.ui.selected=list(self.ui.region_choices()).index('US_SOCAL')
        await self.ui.key('enter');self.assertEqual(self.ui.experimental_choice,0)
        self.assertIsNotNone(self.ui.experimental_entry);self.assertEqual(radio_config(s)['frequency'],927875000)
        await self.ui.key('escape');self.assertFalse(pc.accepted(s,changed))

    async def test_override_never_unlocks_433_or_exceeds_upper_900_mhz_band(self):
        s=self.store
        for key in ('PT_433','EU_433_LONG','EU_433_NARROW'):
            entry=pc.catalog(s)[key];self.assertFalse(pc.experimental(entry))
            with self.assertRaises(ValueError):pc.select_profile(s,entry,allow_experimental=True)
            self.assertIsNone(s.get(pc.ACK_PREFIX+key))
        for frequency in (867000000,928000000,950000000):
            entry=copy.deepcopy(self.entry);entry['radio']['frequency']=frequency
            entry['radio']['tx_power']=pc.default_power(entry['id'],frequency)
            with self.assertRaises(ValueError):pc.select_profile(s,entry,allow_experimental=True)
        for key in ('AU_SA_WA','AU_QLD','BR'):
            self.assertTrue(pc.experimental(pc.catalog(s)[key]))
        self.assertEqual(s.get('region','US'),'US')

    async def test_encrypted_backup_retains_exact_acknowledgement_and_rejects_missing_or_forged_one(self):
        s=self.store;pc.select_profile(s,self.entry,allow_experimental=True)
        path=backup.export(self.tmp.name,'disposable password');data=backup.read(path,'disposable password')
        s.set('region','US')
        with s.db:s.db.execute('DELETE FROM settings WHERE key=?',(pc.ACK_PREFIX+'US_SOCAL',))
        backup.apply_restore(s,data,'disposable password')
        self.assertEqual(radio_config(s)['frequency'],927875000)
        self.assertTrue(pc.accepted(s,self.entry))
        for value in (None,'bad','0'*64):
            bad=copy.deepcopy(data)
            bad['settings']=[r for r in bad['settings'] if r['key']!=pc.ACK_PREFIX+'US_SOCAL']
            if value is not None:bad['settings'].append(dict(key=pc.ACK_PREFIX+'US_SOCAL',value=value))
            with self.subTest(value=value),self.assertRaises(ValueError):backup.validate(bad)
