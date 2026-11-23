"""Upstream preset ingestion, offline behavior and explicit radio selection."""
import asyncio
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'vendor'))
from meshcore_zero import backup
from meshcore_zero.store import Store,radio_config
from meshcore_zero.regions import protocol_config
from meshcore_zero.ui import UI
from meshcore_zero import preset_catalog as pc


def source(title='Test community',frequency='869.618',size=3):
    return {'config':{'suggested_radio_settings':{'entries':[dict(title=title,frequency=frequency,bandwidth='62.5',spreading_factor='7',coding_rate='5',network_settings={'path_hash_size':size})]}}}


class PresetTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);self.addCleanup(self.store.db.close)
        self.ui=UI(self.store)

    async def test_hungary_offline_full_snapshot_and_unsupported_cap_profiles(self):
        entries=pc.bundled_entries();self.assertEqual(len(entries),27)
        entry=pc.catalog(self.store)['HU']
        self.assertEqual(entry['radio'],dict(frequency=869618000,bandwidth=62500,spreading_factor=7,coding_rate=5,tx_power=14))
        self.assertEqual(entry['path_bytes'],2)
        self.ui.screen='regions';self.ui.selected=list(self.ui.region_choices()).index('HU')
        await self.ui.key('enter')
        self.assertEqual(self.store.get('region'),'HU');self.assertEqual(protocol_config(self.store),('',2))
        before=radio_config(self.store)
        for key in ('EU_433_LONG','PT_433','US_SOCAL','AU_SA_WA'):
            with self.assertRaises(ValueError):pc.select_profile(self.store,pc.catalog(self.store)[key])
            self.assertEqual(radio_config(self.store),before)
        self.ui.screen='regions';self.ui.region_catalog=None
        self.ui.selected=list(self.ui.region_choices()).index('PT_433')
        await self.ui.key('enter');self.assertEqual(self.ui.screen,'regions');self.assertEqual(self.store.get('region'),'HU')

    async def test_refresh_adds_future_profiles_without_mutating_legacy_or_selected_radio(self):
        s=self.store;before=radio_config(s);s.set('coding_rate_US',8)
        s.join('#testing');s.add('#testing','Fixture','Retain history')
        rows=pc.parse_api(source())
        with patch.object(pc,'download_entries',new=AsyncMock(return_value=rows)):
            await pc.refresh(self.ui)
        self.assertEqual(radio_config(s),dict(before,coding_rate=8));self.assertEqual(s.get('region','US'),'US')
        entry=pc.catalog(s)[rows[0]['id']];pc.select_profile(s,entry)
        self.assertEqual(protocol_config(s),('',3));old=radio_config(s)
        changed=pc.parse_api(source(frequency='869.432',size=2))
        with patch.object(pc,'download_entries',new=AsyncMock(return_value=changed)):
            await pc.refresh(self.ui,manual=True)
        self.assertEqual(radio_config(s),old);self.assertEqual(protocol_config(s),('',3))
        self.assertEqual(pc.catalog(s)[entry['id']]['radio']['frequency'],869432000)
        self.assertEqual(len(s.history('#testing')),1)
        pc.select_profile(s,pc.catalog(s)[entry['id']]);self.assertEqual(radio_config(s)['frequency'],869432000)
        self.assertEqual(protocol_config(s),('',2))

    async def test_offline_bad_cache_throttle_and_manual_refresh_preserve_selection(self):
        s=self.store;u=self.ui;rows=pc.parse_api(source())
        s.set(pc.CACHE_KEY,json.dumps(rows));s.set(pc.TIME_KEY,'1000')
        with patch.object(pc,'download_entries',new=AsyncMock(return_value=None)) as download,patch.object(pc.time,'time',return_value=1001):
            await pc.refresh(u);download.assert_not_awaited()
            await pc.refresh(u,manual=True);download.assert_awaited_once()
        self.assertEqual(json.loads(s.get(pc.CACHE_KEY)),rows)
        u.screen='regions';u.selected=list(u.region_choices()).index('HU');frozen=list(u.region_choices())
        with patch.object(pc,'download_entries',new=AsyncMock(return_value=rows)):
            await pc.refresh(u,manual=True)
        self.assertEqual(list(u.region_choices())[u.selected],'HU')
        self.assertEqual(u.render().size,(320,170))
        s.set(pc.CACHE_KEY,'not json');u.region_catalog=None
        self.assertIn('HU',u.region_choices());self.assertEqual(s.get('region','US'),'US')

    async def test_encrypted_backup_retains_downloaded_selected_profile_offline(self):
        s=self.store;s.set('identity',bytes(range(32)).hex())
        rows=pc.parse_api(source());entry=rows[0]
        s.set(pc.CACHE_KEY,json.dumps(rows));pc.select_profile(s,entry)
        s.set('scope_'+entry['id'],'local');s.set('path_bytes_'+entry['id'],2)
        path=backup.export(self.tmp.name,'disposable password');data=backup.read(path,'disposable password')
        s.set('region','US')
        with s.db:s.db.execute('DELETE FROM settings WHERE key=?',(pc.CACHE_KEY,))
        backup.apply_restore(s,data,'disposable password')
        self.assertEqual(radio_config(s)['frequency'],869618000);self.assertEqual(protocol_config(s),('local',2))
        for key,value in ((pc.CACHE_KEY,'bad json'),(pc.PROFILE_PREFIX+entry['id'],json.dumps(dict(entry,path_bytes=4)))):
            bad=copy.deepcopy(data);bad['settings']=[r for r in bad['settings'] if r['key']!=key]+[dict(key=key,value=value)]
            with self.assertRaises(ValueError):backup.validate(bad)

    async def test_invalid_upstream_payloads_never_replace_a_good_cache(self):
        for field,value in (('frequency','nan'),('bandwidth','123'),('coding_rate','9'),('spreading_factor','99'),('title','bad\nname')):
            data=source();data['config']['suggested_radio_settings']['entries'][0][field]=value
            with self.subTest(field=field),self.assertRaises((ValueError,TypeError)):pc.parse_api(data)
        for size in (True,0,4,'2'):
            with self.subTest(size=size),self.assertRaises(ValueError):pc.parse_api(source(size=size))
        data=source();data['config']['suggested_radio_settings']['entries']*=2
        with self.assertRaises(ValueError):pc.parse_api(data)
        bad=source();bad['config']['suggested_radio_settings']['entries']=[]
        with self.assertRaises(ValueError):pc.parse_api(bad)

    async def test_fetch_is_bounded_has_user_agent_and_rejects_redirects(self):
        from types import SimpleNamespace
        response=SimpleNamespace(url=pc.API,read=lambda n:json.dumps(source()).encode())
        class Context:
            def __enter__(self):return response
            def __exit__(self,*args):pass
        with patch.object(pc,'urlopen',return_value=Context()) as open_url:
            self.assertEqual(len(pc.fetch_entries()),1)
            request=open_url.call_args.args[0];self.assertIn('MeshCore-Zero',request.get_header('User-agent'))
            response.url='https://example.invalid/'
            with self.assertRaises(ValueError):pc.fetch_entries()
            response.url=pc.API;response.read=lambda n:b'x'*(pc.MAX_BYTES+1)
            with self.assertRaises(ValueError):pc.fetch_entries()

    async def test_cancel_reaps_fetch_child(self):
        from types import SimpleNamespace
        process=SimpleNamespace(returncode=None,kill=lambda:setattr(process,'returncode',-9))
        calls=[]
        async def communicate():
            calls.append(1)
            if len(calls)==1:await asyncio.Future()
            return b'',b''
        process.communicate=communicate
        with patch.object(pc.asyncio,'create_subprocess_exec',new=AsyncMock(return_value=process)):
            task=asyncio.create_task(pc.download_entries());await asyncio.sleep(.01);task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
        self.assertEqual(process.returncode,-9);self.assertEqual(len(calls),2)
