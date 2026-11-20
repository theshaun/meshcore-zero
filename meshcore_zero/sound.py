"""Short, nonblocking message chime through the user's normal audio mixer."""
import asyncio
import logging
from pathlib import Path
import shutil
import time

log = logging.getLogger(__name__)


class MessageSound:
    def __init__(self, store):
        self.store = store
        self.player = shutil.which('paplay') or shutil.which('pw-play')
        self.file = Path(__file__).resolve().parent.parent/'assets/message.wav'
        self.task = None
        self.last_played = float('-inf')

    def received(self):
        if not self.player or self.store.get('message_sound', 'on') != 'on':
            return
        if self.task and not self.task.done() or time.monotonic()-self.last_played < 1:
            return  # Collapse bursts rather than queue a long series of sounds.
        self.last_played = time.monotonic()
        self.task = asyncio.create_task(self.play())

    async def play(self):
        process = None
        try:
            process = await asyncio.create_subprocess_exec(self.player, str(self.file),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            result = await asyncio.wait_for(process.wait(), 4)
            if result:
                log.warning('Message chime player exited with status %s', result)
        except (OSError, asyncio.TimeoutError):
            log.warning('Message chime unavailable', exc_info=True)
        finally:
            if process and process.returncode is None:
                process.kill()
                await process.wait()

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
