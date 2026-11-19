"""Cardputer CAP power and detection, independently implemented from board facts.

New Cap LoRa-1262: PI4IOE5V6408 at 0x43, P0 enables the antenna switch.
Legacy Cap LoRa868: no expander. Both must answer as SX126x on SPI0 CE1.
"""
import errno
import logging
from pathlib import Path
import time

log = logging.getLogger(__name__)

class CapPower:
    def __init__(self):
        self.saved = []
        self.i2c = None
        self.registers = {}
        self.model = 'Unknown CAP'

    def start(self):
        from periphery import I2C
        try:
            for name in ('ext_5v_out', 'grove_5v_out'):
                path = Path('/sys/class/leds') / name / 'brightness'
                if not path.exists(): continue  # Some images use an always-on rail.
                value = path.read_text().strip()
                self.saved.append((path, value))
                if value == '0': path.write_text('1')
            time.sleep(.2)
            try:
                self.i2c = I2C('/dev/i2c-1')
                for attempt in range(10):
                    try:
                        device_id = self.read(1)
                        break
                    except OSError as exc:
                        if exc.errno not in (errno.ENXIO, getattr(errno,'EREMOTEIO',121)): raise
                        if attempt == 9:
                            self.i2c.close(); self.i2c = None
                            self.model = 'Legacy CAP (SPI pending)'
                            return
                        time.sleep(.05)
            except FileNotFoundError:
                self.model = 'Legacy CAP (SPI pending)'
                return
            if device_id & 0xfc != 0xa0:
                raise RuntimeError('Unrecognized CAP expander at 0x43')
            self.registers = {reg: self.read(reg) for reg in (3, 5, 7, 11)}
            # Latch high first; touch only P0 and preserve every other pin.
            for reg, value in ((5,self.registers[5]|1),(11,self.registers[11]&~1),
                               (3,self.registers[3]|1),(7,self.registers[7]&~1)):
                self.write(reg,value)
            if not self.read(5)&1 or not self.read(3)&1 or self.read(7)&1:
                raise RuntimeError('CAP antenna switch readback failed')
            self.model = 'CAP LoRa-1262'
        except Exception:
            self.close()
            raise

    def confirm_radio(self, chip):
        # Read the silicon's version string, not an all-zero/all-one floating bus.
        signature = bytes(chip.readRegister(0x0320,16))
        if not signature.startswith(b'SX126'):
            raise RuntimeError('No SX126x CAP detected; check attachment / SPI')
        if self.i2c is None: self.model = 'Legacy CAP LoRa868'
        return self.model

    def read(self, reg):
        from periphery import I2C
        messages = [I2C.Message([reg]), I2C.Message([0], read=True)]
        self.i2c.transfer(0x43,messages)
        return messages[1].data[0]

    def write(self, reg, value):
        from periphery import I2C
        self.i2c.transfer(0x43,[I2C.Message([reg,value])])

    def close(self):
        if self.i2c:
            # Disable P0 while restoring the latch/direction to avoid glitches.
            try:
                if self.registers: self.write(7,self.read(7)|1)
                for reg in (5,11,3,7):
                    if reg in self.registers:
                        self.write(reg,(self.read(reg)&~1)|(self.registers[reg]&1))
            except Exception:
                log.exception('Restoring CAP antenna switch')
            finally:
                self.i2c.close(); self.i2c = None
        self.registers = {}
        for path,value in reversed(self.saved):
            try: path.write_text(value)
            except Exception: log.exception('Restoring CAP power')
        self.saved.clear()
