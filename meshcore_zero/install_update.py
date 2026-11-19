"""Root helper: stage and validate the exact downloaded package before installing."""
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

def install(path, digest, version):
    if os.geteuid()!=0: raise ValueError('Administrator access required')
    if not re.fullmatch('[0-9a-f]{64}',digest) or not re.fullmatch(r'\d+\.\d+\.\d+',version):
        raise ValueError('Invalid release metadata')
    with tempfile.TemporaryDirectory(prefix='meshcore-install-') as directory:
        target=Path(directory)/'meshcore-zero.deb'
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as src, target.open('wb') as dst:
            info=os.fstat(src.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size>100*1024*1024:
                raise ValueError('Invalid package file')
            sha=hashlib.sha256(); total=0
            while chunk:=src.read(1024*1024):
                total+=len(chunk)
                if total>100*1024*1024: raise ValueError('Package too large')
                sha.update(chunk);dst.write(chunk)
        if sha.hexdigest()!=digest: raise ValueError('Checksum mismatch')
        for field, expected in [('Package','meshcore-zero'),('Architecture','arm64'),('Version',version)]:
            value=subprocess.check_output(['dpkg-deb','-f',str(target),field],text=True).strip()
            if value!=expected: raise ValueError('Wrong package metadata')
        installed=subprocess.check_output(['dpkg-query','-W','-f=${Version}','meshcore-zero'],text=True).strip()
        if subprocess.run(['dpkg','--compare-versions',version,'lt',installed]).returncode==0:
            raise ValueError('Downgrade refused')
        log_fd=os.open('/var/log/meshcore-zero-update.log',os.O_WRONLY|os.O_CREAT|os.O_APPEND|os.O_NOFOLLOW,0o600)
        with os.fdopen(log_fd,'ab') as log:
            subprocess.run(['apt-get','install','-y','--no-remove',str(target)],check=True,
                env={**os.environ,'DEBIAN_FRONTEND':'noninteractive'},stdout=log,stderr=log,stdin=subprocess.DEVNULL)

if __name__=='__main__':
    try: install(*sys.argv[1:])
    except Exception: sys.exit(1)
