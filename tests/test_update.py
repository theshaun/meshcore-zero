import asyncio
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from meshcore_zero.update import Updater, REPO, version
from meshcore_zero.ui import UI, GREEN, UNCONFIRMED
from meshcore_zero.store import Store

class UpdateTests(unittest.TestCase):
    def release(self):
        names=['meshcore-zero_0.1.9_arm64.deb','SHA256SUMS']
        return json.dumps({'tag_name':'v0.1.9','assets':[{'name':n,'browser_download_url':REPO+'/releases/download/v0.1.9/'+n} for n in names]}).encode()

    def test_version_and_release_validation(self):
        self.assertGreater(version('0.1.10'),version('v0.1.9'))
        with self.assertRaises(ValueError): version('1.2.3;echo bad')
        u=Updater('0.1.8')
        with patch('meshcore_zero.update.fetch',return_value=self.release()): self.assertTrue(u.check())
        invalid=json.loads(self.release());invalid['assets'][0]['browser_download_url']='https://example.com/app.deb'
        with patch('meshcore_zero.update.fetch',return_value=json.dumps(invalid).encode()):
            with self.assertRaises(ValueError): u.check()
        with patch('meshcore_zero.update.fetch',return_value=self.release()): self.assertFalse(Updater('0.1.10').check())

    def test_download_integrity_and_cleanup(self):
        u=Updater('0.1.8');payload=b'package test';sha=hashlib.sha256(payload).hexdigest()
        with patch('meshcore_zero.update.fetch',return_value=self.release()):u.check()
        manifest=(sha+'  '+u.release[1]+'\n').encode()
        with patch('meshcore_zero.update.fetch',side_effect=[manifest,payload]): u.download()
        path=u.path;self.assertEqual(path.read_bytes(),payload);self.assertEqual(path.stat().st_mode&0o777,0o600)
        u.cleanup();self.assertFalse(path.exists())
        with patch('meshcore_zero.update.fetch',side_effect=[manifest,b'corrupted']):
            with self.assertRaises(ValueError):u.download()
        self.assertIsNone(u.path)

    def test_password_is_masked_and_not_persisted(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root);ui=UI(store);ui.screen='update';ui.update_state='password'
            asyncio.run(ui.key('x'));self.assertEqual(ui.password,'x');self.assertEqual(ui.draft,'')
            ui.render()
            asyncio.run(ui.key('escape'));self.assertEqual(ui.password,'');self.assertEqual(ui.drafts,{})
            self.assertNotIn('password',[r[0] for r in store.db.execute('select key from settings')]);store.db.close()

    def test_indicator_color_and_size(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root);store.join('#testing');mid=store.add('#testing','Zero','Hi',status='sent')
            ui=UI(store);ui.open_chat(next(c for c in store.chats() if c['id']=='#testing'))
            self.assertEqual(ui.chat_lines(store.history('#testing'))[0][0],('● ',UNCONFIRMED))
            store.bind_tx(mid,'hash');store.heard('hash',0)
            self.assertEqual(ui.chat_lines(store.history('#testing'))[0][0],('● ',GREEN))
            image=ui.render();color=tuple(bytes.fromhex(GREEN[1:]));pixels=[(x,y) for y in range(37,50) for x in range(10,18) if image.getpixel((x,y))==color]
            self.assertTrue(pixels);self.assertLessEqual(len(pixels),16);store.db.close()

    def test_root_helper_rejects_wrong_hash_and_package(self):
        from meshcore_zero.install_update import install
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'update.deb';path.write_bytes(b'fake package')
            sha=hashlib.sha256(path.read_bytes()).hexdigest()
            with patch('meshcore_zero.install_update.os.geteuid',return_value=0):
                with self.assertRaises(ValueError): install(str(path),'0'*64,'0.1.9')
                with patch('meshcore_zero.install_update.subprocess.check_output',return_value='wrong-package'):
                    with self.assertRaises(ValueError): install(str(path),sha,'0.1.9')
                link=Path(root)/'symlink';link.symlink_to(path)
                with self.assertRaises(OSError):install(str(link),sha,'0.1.9')
