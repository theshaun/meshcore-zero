"""Honor APPLaunch DarkTime without changing the user's system configuration."""
import asyncio
import json
import logging
from pathlib import Path
import time

log = logging.getLogger(__name__)


class ScreenIdle:
    def __init__(self, config=None, backlight=None, clock=time.monotonic):
        self.config = config or Path.home()/'.config/cardputerzero/config.json'
        self.backlight = backlight or Path('/sys/class/backlight/backlight/brightness')
        self.clock = clock
        self.last_activity = clock()
        self.next_refresh = 0
        self.timeout = 30
        self.brightness = 40
        self.sleeping = False
        self.owned = False
        self.failed = False
        self.lock = asyncio.Lock()

    def tick(self):
        if self.failed:
            return
        now = self.clock()
        try:
            if now >= self.next_refresh:
                try:
                    settings = json.loads(self.config.read_text())
                    timeout = int(settings.get('dark_time', 30))
                    if timeout >= 0:
                        self.timeout = timeout  # Zero is the launcher's Never setting.
                    saved = int(settings.get('brightness', self.brightness))
                    if saved > 0:
                        self.brightness = saved
                except (OSError, ValueError, TypeError, AttributeError):
                    pass  # A missing/temporarily replaced config uses the last value.
                self.next_refresh = now + 2
            current = int(self.backlight.read_text())
            if current > 0:
                self.brightness = current
                self.sleeping = False
                self.owned = False
            else:
                self.sleeping = True
            if not self.timeout:
                self.restore()
            elif not self.sleeping and now-self.last_activity >= self.timeout:
                self.backlight.write_text('0')
                self.sleeping = self.owned = True
                log.info('Display asleep after DarkTime=%ss; radio remains active', self.timeout)
        except (OSError, ValueError):
            log.warning('Screen timeout unavailable', exc_info=True)
            self.failed = True

    def restore(self):
        if self.owned:
            if int(self.backlight.read_text()) == 0:
                self.backlight.write_text(str(self.brightness))
            self.sleeping = self.owned = False

    async def activity(self):
        async with self.lock:
            self.last_activity = self.clock()
            if not self.sleeping:
                return False
            try:
                await asyncio.to_thread(self.backlight.write_text, str(self.brightness))
                self.sleeping = self.owned = False
                return True  # Consume the wake-up key instead of sending/activating it.
            except OSError:
                log.warning('Could not wake display', exc_info=True)
                return True

    async def run(self):
        while True:
            async with self.lock:
                await asyncio.to_thread(self.tick)
            await asyncio.sleep(.25)

    async def close(self):
        try:
            await asyncio.to_thread(self.restore)
        except (OSError, ValueError):
            log.warning('Could not restore display on exit', exc_info=True)
