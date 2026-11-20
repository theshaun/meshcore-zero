import asyncio
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock,Mock,patch
from meshcore_zero.update import Updater,open_download
from meshcore_zero.update_log import TimingLog
from meshcore_zero.install_update import apt_progress,run_apt,Progress,private_cache,emit_event,private_cache
from meshcore_zero.store import Store
from meshcore_zero.ui import UI
from test_update import Response

class DownloadTests(unittest.TestCase):
    def make_updater(self,root):
        updater=Updater(log_path=Path(root)/'update.log',cache_dir=Path(root)/'cache')
        updater.release=('0.1.19','meshcore-zero_0.1.19_arm64.deb','https://example.invalid/deb','https://example.invalid/sums')
        return updater

    def test_streaming_known_and_unknown_length_progress_and_timings(self):
        payload=b'x'*(128*1024+17)
        for headers in ({'Content-Length':str(len(payload))},{}):
            with tempfile.TemporaryDirectory() as tmp:
                u=self.make_updater(tmp);events=[]
                manifest=(hashlib.sha256(payload).hexdigest()+'  '+u.release[1]+'\n').encode()
                with patch('meshcore_zero.update.fetch',return_value=manifest),patch('meshcore_zero.update.open_download',return_value=Response(payload,headers)):
                    u.download(lambda *args:events.append(args))
                try:
                    self.assertEqual(u.path.parent.parent,Path(tmp)/'cache');self.assertEqual(u.cache_dir.stat().st_mode&0o777,0o700)
                    self.assertEqual(u.path.read_bytes(),payload);self.assertEqual(u.path.stat().st_mode&0o777,0o600)
                    expected=len(payload) if headers else None
                    self.assertIn(('download',len(payload),expected),events)
                    self.assertEqual([e[0] for e in events if e[1] is None],['manifest','connect','download','verify_download'])
                    records=[json.loads(line) for line in (Path(tmp)/'update.log').read_text().splitlines()]
                    self.assertEqual([r['stage'] for r in records],['manifest','connect','download','verify_download'])
                    self.assertTrue(all(r['status']=='ok' for r in records))
                finally:u.cleanup()

    def test_truncated_oversized_and_bad_checksum_downloads_are_removed(self):
        for payload,headers,limit in [(b'abc',{'Content-Length':'4'},100),(b'abcdef',{},5),(b'bad',{},100)]:
            with tempfile.TemporaryDirectory() as tmp:
                u=self.make_updater(tmp)
                manifest=(hashlib.sha256(b'good').hexdigest()+'  '+u.release[1]+'\n').encode()
                with patch('meshcore_zero.update.fetch',return_value=manifest),patch('meshcore_zero.update.open_download',return_value=Response(payload,headers)),patch('meshcore_zero.update.MAX_PACKAGE_BYTES',limit):
                    with self.assertRaises(ValueError):u.download()
                self.assertIsNone(u.path);self.assertIsNone(u.directory)
                records=[json.loads(line) for line in (Path(tmp)/'update.log').read_text().splitlines()]
                self.assertEqual(records[-1]['status'],'error')

    def test_http_redirect_is_refused(self):
        response=Response(b'unsafe');response.url='http://example.invalid/package'
        with patch('meshcore_zero.update.urlopen',return_value=response):
            with self.assertRaises(ValueError):open_download('https://example.invalid/package')
        self.assertTrue(response.closed)

    def test_log_is_private_bounded_and_only_contains_timing_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'update.log';path.write_text('x'*300000)
            TimingLog(path).record('download',1.25)
            entry=json.loads(path.read_text())
            self.assertEqual(set(entry),{'time','stage','seconds','status'})
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertTrue(path.with_name('update.log.1').exists())

class InstallTests(unittest.IsolatedAsyncioTestCase):
    async def test_install_streams_stages_and_logs_without_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            u=Updater(log_path=Path(tmp)/'update.log');u.path=Path(tmp)/'package';u.digest='a'*64;u.release=('0.1.19',)
            events=[dict(event='progress',stage='stage_package',percent=None),dict(event='timing',stage='stage_package',seconds=.25,status='ok'),dict(event='progress',stage='installing',percent=42),dict(event='timing',stage='installing',seconds=8.5,status='ok')]
            stdin=SimpleNamespace(write=Mock(),drain=AsyncMock(),close=Mock())
            proc=SimpleNamespace(stdin=stdin,stdout=SimpleNamespace(readline=AsyncMock(side_effect=[*(json.dumps(e).encode()+b'\n' for e in events),b''])),returncode=0,wait=AsyncMock())
            received=[]
            with patch('meshcore_zero.update.asyncio.create_subprocess_exec',new=AsyncMock(return_value=proc)):
                await u.install('sensitive-example',lambda *args:received.append(args))
            self.assertIn(('installing',42,100),received)
            text=(Path(tmp)/'update.log').read_text();self.assertNotIn('sensitive-example',text)
            self.assertIn('install_total',text);self.assertIn('8.5',text)

    async def test_authentication_failure_logs_failure_without_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            u=Updater(log_path=Path(tmp)/'update.log');u.path=Path(tmp)/'package';u.digest='a'*64;u.release=('0.1.19',)
            stdin=SimpleNamespace(write=Mock(),drain=AsyncMock(),close=Mock())
            proc=SimpleNamespace(stdin=stdin,stdout=SimpleNamespace(readline=AsyncMock(return_value=b'')),returncode=1,wait=AsyncMock())
            with patch('meshcore_zero.update.asyncio.create_subprocess_exec',new=AsyncMock(return_value=proc)):
                with self.assertRaises(ValueError):await u.install('sensitive-example')
            records=[json.loads(line) for line in (Path(tmp)/'update.log').read_text().splitlines()]
            self.assertEqual([r['status'] for r in records],['error','error'])
            self.assertNotIn('sensitive-example',str(records))

    def test_private_installer_cache_permissions_and_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=private_cache(Path(tmp)/'cache')
            self.assertEqual(path.stat().st_mode&0o777,0o700)
            link=Path(tmp)/'link';link.symlink_to(path,target_is_directory=True)
            with self.assertRaises(ValueError):private_cache(link)

    def test_closed_ui_pipe_does_not_abort_the_privileged_installer(self):
        with patch('meshcore_zero.install_update.os.write',side_effect=BrokenPipeError):
            report=Progress(emit_event)
            report.enter('installing',50)
            report.finish('ok')

    def test_installer_cache_is_private_and_refuses_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cache=private_cache(root/'cache')
            self.assertEqual(cache.stat().st_mode&0o777,0o700)
            link=root/'link';link.symlink_to(cache,target_is_directory=True)
            with self.assertRaises(ValueError):private_cache(link)

    async def test_authentication_failure_logs_error_without_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            u=Updater(log_path=Path(tmp)/'update.log');u.path=Path(tmp)/'package';u.digest='a'*64;u.release=('0.1.19',)
            proc=SimpleNamespace(stdin=SimpleNamespace(write=Mock(),drain=AsyncMock(),close=Mock()),
                stdout=SimpleNamespace(readline=AsyncMock(return_value=b'')),returncode=1,wait=AsyncMock())
            with patch('meshcore_zero.update.asyncio.create_subprocess_exec',new=AsyncMock(return_value=proc)):
                with self.assertRaises(ValueError):await u.install('wrong-example-password')
            text=(Path(tmp)/'update.log').read_text()
            self.assertNotIn('wrong-example-password',text)
            records=[json.loads(line) for line in text.splitlines()]
            self.assertEqual([r['stage'] for r in records],['authenticate','install_total'])
            self.assertTrue(all(r['status']=='error' for r in records))

    def test_apt_machine_progress_parser_and_pipe(self):
        self.assertEqual(apt_progress('dlstatus:1:25.5:private details'),('dependencies',25.5))
        self.assertEqual(apt_progress('pmstatus:package:80:private details'),('installing',80))
        for line in ('pmstatus:x:nan:text','pmstatus:x:101:text','pmerror:x:0:secret','broken'):
            self.assertIsNone(apt_progress(line))
        events=[]
        def start(args,**kwargs):
            os.write(kwargs['pass_fds'][0],b'dlstatus:1:25:private\npmstatus:pkg:80:private\n')
            self.assertIn('--no-remove',args)
            return SimpleNamespace(wait=lambda:0)
        with tempfile.TemporaryFile() as log,patch('meshcore_zero.install_update.subprocess.Popen',side_effect=start):
            report=Progress(events.append);run_apt(Path('/tmp/package.deb'),log,report);report.finish('ok')
        self.assertTrue(any(e.get('stage')=='installing' and e.get('percent')==80 for e in events))
        self.assertNotIn('private',json.dumps(events))

class ProgressUiTests(unittest.TestCase):
    def test_live_elapsed_bytes_unknown_size_and_password_states_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp)
            try:
                ui=UI(store);ui.screen='update';ui.update_state='busy';ui.update_started=10
                ui.update_progress('download',1048576,2097152)
                with patch('meshcore_zero.ui.time.monotonic',return_value=20):
                    before=ui.render_key();self.assertEqual(ui.render().size,(320,170))
                with patch('meshcore_zero.ui.time.monotonic',return_value=21):self.assertNotEqual(before,ui.render_key())
                ui.update_progress('download',1048576,None);ui.render()
                ui.update_state='password';ui.password='private-password'
                with patch.object(ui.text,'draw',wraps=ui.text.draw) as draw:ui.render()
                self.assertNotIn('private-password',str(draw.call_args_list))
            finally:store.db.close()
