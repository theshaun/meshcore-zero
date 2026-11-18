"""Linux framebuffer and evdev, without requiring an X server or root."""
import fcntl
import glob
import mmap
import os
import struct


class Framebuffer:
    def __init__(self, device=None):
        device = device or os.getenv('APPLAUNCH_LINUX_FBDEV_DEVICE') or os.getenv('LV_LINUX_FBDEV_DEVICE') or '/dev/fb_lcd'
        self.fd = os.open(device, os.O_RDWR)
        try:
            var = bytearray(160)
            fcntl.ioctl(self.fd,0x4600,var)
            self.width,self.height,_,_,self.xoff,self.yoff,self.bpp=struct.unpack_from('7I',var)
            self.fields = [struct.unpack_from('3I', var, offset) for offset in (32,44,56)]
            fix=bytearray(80)
            fcntl.ioctl(self.fd,0x4602,fix)
            self.stride=struct.unpack_from('I',fix,48)[0]
            if (self.width,self.height)!=(320,170) or self.bpp not in (16,32):
                raise RuntimeError(f'Unsupported framebuffer {self.width}x{self.height}/{self.bpp}')
            smem_len = struct.unpack_from('I',fix,16+struct.calcsize('L'))[0]
            self.memory = mmap.mmap(self.fd, smem_len, flags=mmap.MAP_SHARED,
                prot=mmap.PROT_READ | mmap.PROT_WRITE)
        except BaseException:
            os.close(self.fd)
            raise

    def write(self, image):
        pixels=bytearray()
        for rgb in image.getdata():
            value=0
            for channel,(offset,length,_) in zip(rgb,self.fields):
                value |= (channel >> (8-length)) << offset
            pixels.extend(value.to_bytes(self.bpp//8,'little'))
        rowbytes=self.width*self.bpp//8
        for y in range(self.height):
            offset=(y+self.yoff)*self.stride+self.xoff*self.bpp//8
            # panel-mipi-dbi's deferred refresh tracks dirty mapped pages.
            # pwrite changes readback memory but can leave the physical LCD stale.
            self.memory[offset:offset+rowbytes]=pixels[y*rowbytes:(y+1)*rowbytes]

    def close(self):
        try:
            self.memory.close()
        finally:
            os.close(self.fd)


class Keyboard:
    # Linux keycodes. Fn arrows also arrive as KEY_UP/DOWN on the Zero.
    SPECIAL={1:'escape',14:'backspace',15:'tab',28:'enter',103:'up',108:'down',105:'left',106:'right'}
    CHARS=dict(zip(range(2,14),'1234567890-='))
    CHARS.update(dict(zip(range(16,28),'qwertyuiop[]')))
    CHARS.update(dict(zip(range(30,42),"asdfghjkl;'`")))
    CHARS.update(dict(zip(range(44,54),'zxcvbnm,./')))
    CHARS.update({43:'\\',57:' '})
    SHIFT=dict(zip("1234567890-=[];'`,./\\",'!@#$%^&*()_+{}:"~<>?|'))
    # The Zero's Sym layer emits custom Linux codes, rather than a US layout.
    SYMBOLS=dict(zip(
        (26,27,39,40,41,43,51,52,53,94,55,69,70,71,72,73,74,75,76,77,79,80,81,82,83,85,86,89,90,91,92,93),
        '!@#$%^&*()~`_-+=[]{};:\'"<>\\|,./?'))

    def __init__(self):
        self.fd=None
        for path in glob.glob('/sys/class/input/event*/device/name'):
            if 'tca8418' in open(path).read().lower():
                self.fd=os.open('/dev/input/'+path.split('/')[4],os.O_RDONLY|os.O_NONBLOCK)
                break
        if self.fd is None: raise RuntimeError('Cardputer keyboard not found')
        # Prevent keys leaking into launcher while the client owns the screen.
        self.grabbed = not os.getenv('APPLAUNCH_LINUX_KEYBOARD_DEVICE')
        if self.grabbed:
            fcntl.ioctl(self.fd,0x40044590,1)
        self.shift=set()
        self.buffer=b''

    def read(self):
        result=[]
        try: self.buffer+=os.read(self.fd,4096)
        except BlockingIOError: return result
        size=struct.calcsize('llHHi')
        while len(self.buffer)>=size:
            _,_,kind,code,value=struct.unpack('llHHi',self.buffer[:size])
            self.buffer=self.buffer[size:]
            key=self.translate(kind,code,value)
            if key is not None: result.append(key)
        return result

    def translate(self,kind,code,value):
        if kind!=1: return None
        if code in (42,54):
            self.shift.add(code) if value else self.shift.discard(code)
            return None
        if value not in (1,2): return None
        if code in self.SYMBOLS: return self.SYMBOLS[code]
        if code in self.SPECIAL: return self.SPECIAL[code]
        if code in self.CHARS:
            char=self.CHARS[code]
            return self.SHIFT.get(char,char.upper()) if self.shift else char
        return None

    def close(self):
        if self.grabbed: fcntl.ioctl(self.fd,0x40044590,0)
        os.close(self.fd)
