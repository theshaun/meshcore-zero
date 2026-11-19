"""GitHub releases updater; no account, telemetry, or device credentials persisted."""
import asyncio
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen
from . import __version__

REPO = 'https://github.com/unagisan69/meshcore-zero'
API = 'https://api.github.com/repos/unagisan69/meshcore-zero/releases/latest'

def version(value):
    if not re.fullmatch(r'v?\d+\.\d+\.\d+', value):
        raise ValueError('Unsupported release version')
    return tuple(map(int, value.lstrip('v').split('.')))

def fetch(url, limit):
    with urlopen(Request(url, headers={'User-Agent': 'MeshCore-Zero-updater', 'Accept': 'application/vnd.github+json'}), timeout=20) as response:
        if not response.url.startswith('https://'):
            raise ValueError('Insecure download refused')
        data = response.read(limit+1)
        if len(data)>limit: raise ValueError('Download exceeds size limit')
        return data

class Updater:
    def __init__(self, current=__version__):
        self.current = current
        self.release = None
        self.directory = None
        self.path = None
        self.digest = None

    def check(self):
        release = json.loads(fetch(API, 1024*1024))
        tag = release['tag_name']
        if release.get('draft') or release.get('prerelease'):
            raise ValueError('No published update available')
        self.release = None
        if version(tag)<=version(self.current): return False
        name = f'meshcore-zero_{tag.lstrip("v")}_arm64.deb'
        assets = {a['name']:a['browser_download_url'] for a in release['assets']}
        for asset in (name, 'SHA256SUMS'):
            if assets.get(asset)!=f'{REPO}/releases/download/{tag}/{asset}':
                raise ValueError('Release files are incomplete')
        self.release = (tag.lstrip('v'), name, assets[name], assets['SHA256SUMS'])
        return True

    def download(self):
        if not self.release: raise ValueError('Check for an update first')
        ver, name, url, sums = self.release
        lines = fetch(sums, 65536).decode().splitlines()
        matches = [line.split()[0] for line in lines if len(line.split())==2 and line.split()[1].lstrip('*')==name]
        if len(matches)!=1 or not re.fullmatch('[0-9a-f]{64}', matches[0]):
            raise ValueError('Release checksum missing')
        self.cleanup()
        self.directory = Path(tempfile.mkdtemp(prefix='meshcore-update-'))
        self.path = self.directory/name
        try:
            data = fetch(url, 100*1024*1024)
            self.digest = hashlib.sha256(data).hexdigest()
            if self.digest!=matches[0]: raise ValueError('Download checksum mismatch')
            self.path.write_bytes(data)
            self.path.chmod(0o600)
        except Exception:
            self.cleanup()
            raise

    async def install(self, password=''):
        if not self.path: raise ValueError('Download an update first')
        helper = Path(__file__).with_name('install_update.py')
        process = await asyncio.create_subprocess_exec('sudo','-S','-p','','/usr/bin/python3',str(helper),str(self.path),self.digest,self.release[0],
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL,start_new_session=True)
        await process.communicate((password+'\n').encode())
        if process.returncode: raise ValueError('Install failed. Check password / update log.')
        self.cleanup()

    def cleanup(self):
        if self.directory: shutil.rmtree(self.directory,ignore_errors=True)
        self.directory = self.path = None
