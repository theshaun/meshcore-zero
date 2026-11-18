#!/usr/bin/env python3
"""Build an offline-installable APPLaunch .deb on ARM64 Debian/Python 3.13."""
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    if platform.machine() not in ('aarch64','arm64') or sys.version_info[:2] != (3,13) or sys.platform!='linux':
        raise SystemExit('Package on ARM64 Linux with Python 3.13 (Zero or GitHub Actions).')
    os.chdir(ROOT)
    config=json.loads((ROOT/'app-builder.json').read_text())
    stage=ROOT/'build/stage'
    if stage.exists(): shutil.rmtree(stage)
    app=stage/'usr/share/meshcore-zero'
    app.mkdir(parents=True)
    runtime=ROOT/'build/runtime'
    if not (runtime/'.complete').exists():
        if runtime.exists(): shutil.rmtree(runtime)
        subprocess.run([sys.executable,'-m','pip','install','--only-binary=:all:', '--target',str(runtime),'-r','requirements-radio.lock'],check=True)
        (runtime/'.complete').touch()
    for name in ('meshcore_zero','vendor','assets'):
        shutil.copytree(ROOT/name,app/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copytree(runtime,app/'runtime',ignore=shutil.ignore_patterns('__pycache__','*.pyc','.complete'))
    shutil.copy2(ROOT/'LICENSE',app/'LICENSE')
    shutil.copy2(ROOT/'THIRD_PARTY_NOTICES.md',app/'THIRD_PARTY_NOTICES.md')
    def write(path,text,mode=0o644):
        target=stage/path
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(text)
        target.chmod(mode)
    write('usr/share/APPLaunch/bin/meshcore-zero',(ROOT/'meshcore-zero').read_text(),0o755)
    write('usr/share/APPLaunch/applications/meshcore-zero.desktop','''[Desktop Entry]
Name=MeshCore
Exec=/usr/share/APPLaunch/bin/meshcore-zero
Terminal=false
Sysplause=true
Icon=share/images/meshcore-zero.png
Type=Application
''')
    icon=stage/'usr/share/APPLaunch/share/images/meshcore-zero.png'
    icon.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/'packaging/icon.png',icon)
    write('DEBIAN/control',f'''Package: meshcore-zero
Version: {config['version']}
Architecture: arm64
Maintainer: unagisan69 <unagisan69@users.noreply.github.com>
Section: APPLaunch
Priority: optional
Depends: python3 (>= 3.13), python3 (<< 3.14), python3-pil, python3-spidev (>= 3.6), fonts-dejavu-core
Homepage: https://github.com/unagisan69/meshcore-zero
Description: Standalone MeshCore client for Cardputer Zero and LoRa CAP
 Combined channels and direct messages with local encrypted radio transport.
''')
    out=ROOT/'dist'/f"meshcore-zero_{config['version']}_arm64.deb"
    out.parent.mkdir(exist_ok=True)
    subprocess.run(['dpkg-deb','-Zgzip','-z6','--root-owner-group','--build',str(stage),str(out)],check=True)
    print(out)


if __name__=='__main__': main()
