"""CAP GNSS input only: checksum-checked NMEA, no receiver commands or GPS logs."""
import asyncio
from dataclasses import dataclass
import fcntl
import math
import os
from pathlib import Path
import termios
import time

FRESH_SECONDS=15
LAST_FIX_SECONDS=300
BROADCAST_SECONDS=15*60

@dataclass(frozen=True)
class Fix:
    latitude:float
    longitude:float
    updated:float


def coordinate(value,hemisphere,latitude):
    if hemisphere not in (('N','S') if latitude else ('E','W')):raise ValueError()
    digits=2 if latitude else 3
    if len(value)<digits+2 or not value[:digits+2].isdigit():raise ValueError()
    degrees=int(value[:digits]);minutes=float(value[digits:])
    if not math.isfinite(minutes) or not 0<=minutes<60:raise ValueError()
    result=degrees+minutes/60
    if not 0<=result<=(90 if latitude else 180):raise ValueError()
    return -result if hemisphere in ('S','W') else result

class NMEA:
    def __init__(self):self.fix=None;self.last_fix=None;self.satellites=None;self.sentences=0
    def feed(self,line,now=None):
        now=time.monotonic() if now is None else now
        try:
            line=line.decode('ascii').strip() if isinstance(line,bytes) else line.strip()
            if not line.isascii() or not 9<=len(line)<=256 or not line.startswith('$') or line.count('*')!=1:return False
            body,check=line[1:].split('*')
            if len(check)!=2 or any(c not in '0123456789abcdefABCDEF' for c in check):return False
            checksum=0
            for ch in body:checksum^=ord(ch)
            if checksum!=int(check,16):return False
            f=body.split(',');kind=f[0]
            if len(kind)!=5 or kind[:2] not in ('GP','GN','GL','GA','GB','BD','GQ'):return False
            if kind[2:]=='GGA':
                if len(f)<10:return False
                quality=int(f[6]);sats=int(f[7] or '0')
                if not 0<=sats<=99:return False
                self.satellites=sats
                if quality not in (1,2,3,4,5):self.fix=None;self.sentences+=1;return True
                lat=coordinate(f[2],f[3],True);lon=coordinate(f[4],f[5],False)
            elif kind[2:]=='RMC':
                if len(f)<10:return False
                if f[2]!='A' or len(f)>12 and f[12] not in ('','A','D','F','R','P'):self.fix=None;self.sentences+=1;return True
                lat=coordinate(f[3],f[4],True);lon=coordinate(f[5],f[6],False)
            else:return False
            self.fix=self.last_fix=Fix(lat,lon,now);self.sentences+=1;return True
        except (ValueError,UnicodeError,IndexError,TypeError):return False
    def fresh(self,now=None):
        now=time.monotonic() if now is None else now
        return self.fix if self.fix and 0<=now-self.fix.updated<=FRESH_SECONDS else None

class SerialInput:
    """Restore UART settings on close; never transmit bytes to the receiver."""
    def __init__(self,path='/dev/serial0'):
        self.fd=None;self.previous=None;self.buffer=b''
        try:
            self.fd=os.open(path,os.O_RDONLY|os.O_NONBLOCK|os.O_NOCTTY|os.O_CLOEXEC)
            fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.previous=termios.tcgetattr(self.fd)
            config=list(self.previous);config[6]=list(config[6])
            config[0]=config[1]=config[3]=0;config[2]=termios.CS8|termios.CREAD|termios.CLOCAL
            config[4]=config[5]=termios.B115200;config[6][termios.VMIN]=0;config[6][termios.VTIME]=0
            termios.tcsetattr(self.fd,termios.TCSANOW,config);termios.tcflush(self.fd,termios.TCIFLUSH)
        except BaseException:self.close();raise
    def read(self):
        try:data=os.read(self.fd,16384)
        except BlockingIOError:return []
        self.buffer+=data
        lines=self.buffer.split(b'\n');self.buffer=lines.pop()[-512:]
        return [line for line in lines if len(line)<=256]
    def close(self):
        if self.fd is not None:
            try:
                if self.previous is not None:termios.tcsetattr(self.fd,termios.TCSANOW,self.previous)
            except (OSError,termios.error):pass
            finally:os.close(self.fd);self.fd=None

async def port_available():
    try:
        cmdline=Path('/proc/cmdline').read_text()
        if any(part.startswith(('console=ttyS0','console=serial0','console=ttyAMA0')) for part in cmdline.split()):return False
        p=await asyncio.create_subprocess_exec('systemctl','is-active','gpsd.service','gpsd.socket','serial-getty@ttyS0.service',stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
        try:output,_=await asyncio.wait_for(p.communicate(),3)
        except BaseException:
            if p.returncode is None:p.kill()
            await p.communicate();raise
        return not any(s in ('active','activating','reloading') for s in output.decode().split())
    except (OSError,asyncio.TimeoutError):return False

class GPS:
    def __init__(self,ui):
        self.ui=ui;self.parser=NMEA();self.status='GPS idle';self.serial=None
        self.last_broadcast=float('-inf');self.retry_at=0
    def fresh(self):return self.parser.fresh()
    def revision(self):
        fix=self.fresh();last=self.parser.last_fix
        return (self.status,self.parser.satellites,(round(fix.latitude,5),round(fix.longitude,5)) if fix else None,int(time.monotonic()-last.updated)//10 if last else None)
    async def run(self,startup_advert=None):
        retry=0
        try:
            while self.ui.running:
                backend=self.ui.backend
                ready=backend and backend.engine and backend.engine.is_running
                wanted=self.ui.screen.startswith('map') or self.ui.screen=='gps_sharing' or self.ui.store.get('gps_broadcast','off')=='on'
                if not ready or not wanted:
                    self.close();self.status='GPS idle' if ready else 'GPS needs active CAP'
                elif self.serial is None and time.monotonic()>=retry:
                    retry=time.monotonic()+10
                    if await port_available():
                        try:self.serial=SerialInput('/dev/serial0' if Path('/dev/serial0').exists() else '/dev/ttyS0');self.status='Waiting for GPS'
                        except (OSError,termios.error):self.status='GPS port unavailable'
                    else:self.status='GPS port busy'
                if self.serial:
                    try:
                        for line in self.serial.read():self.parser.feed(line)
                        self.status='GPS fix' if self.fresh() else 'Waiting for GPS'
                    except (OSError,termios.error):self.close();self.status='GPS disconnected';retry=time.monotonic()+10
                if ready:
                    backend.update_location_policy()
                    now=time.monotonic()
                    if (self.serial and self.ui.store.get('gps_broadcast','off')=='on' and self.fresh()
                        and (startup_advert is None or startup_advert.done())
                        and not self.ui.launch_state and not self.ui.startup_release and self.ui.screen!='update'
                        and now>=max(self.last_broadcast+BROADCAST_SECONDS,self.retry_at)
                        and not backend.send_lock.locked()):
                        self.retry_at=now+60
                        try:await backend.announce(notify=False)
                        except Exception:pass  # The normal radio state remains available; never log coordinates.
                await asyncio.sleep(.2)
        finally:self.close()
    def close(self):
        if self.serial:self.serial.close();self.serial=None

class LocationPrivacyMixin:
    """Recheck sharing immediately before SX1262 SetTx, including queued adverts."""
    def __init__(self,*args,**kwargs):
        self.location_allowed=None;self._location_lock=asyncio.Lock();self._location_packet=None
        super().__init__(*args,**kwargs)
    async def send(self,data):
        async with self._location_lock:
            self._location_packet=data
            try:return await super().send(data)
            finally:self._location_packet=None
    async def _execute_transmission(self,*args,**kwargs):
        if self.location_allowed and not self.location_allowed(self._location_packet):
            raise RuntimeError('Location advert cancelled: sharing off or GPS stale')
        return await super()._execute_transmission(*args,**kwargs)
