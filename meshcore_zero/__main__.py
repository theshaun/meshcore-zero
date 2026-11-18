import argparse
import asyncio
import logging
import os
from pathlib import Path
import signal
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'vendor'))
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'runtime'))

from .store import Store
from .ui import UI


async def run(args):
    directory = args.data or str(Path(os.getenv('XDG_DATA_HOME', str(Path.home()/'.local/share'))) / 'meshcore-zero')
    store=Store(directory)
    ui=UI(store)
    if args.demo:
        store.join('#meshcore')
        store.dm('a'*64,'Mom')
        store.add('public','Alex','Anyone out on the mesh today?')
        store.add('a'*64,'Mom','Are you coming over for dinner?')
        store.add('#meshcore','Sam','Hello from my Cardputer Zero!')
    if args.screenshot:
        ui.render().save(args.screenshot)
        store.db.close()
        return
    from .hardware import Framebuffer,Keyboard
    from .radio import Backend
    fb=keyboard=None
    backend=Backend(store,ui.notice)
    ui.backend=backend
    loop=asyncio.get_running_loop()
    for sig in (signal.SIGTERM,signal.SIGINT):
        loop.add_signal_handler(sig,lambda:setattr(ui,'running',False))
    try:
        fb=Framebuffer()
        keyboard=Keyboard()
        ui.render()  # warm font cache before radio startup
        startup=asyncio.create_task(backend.start())
        previous=None
        started=loop.time()
        while ui.running and (not args.duration or loop.time()-started<args.duration):
            for key in keyboard.read():
                await ui.key(key)
            frame=ui.render()
            data=frame.tobytes()
            if data!=previous:
                fb.write(frame)
                previous=data
            await asyncio.sleep(0.05)
        await startup
    finally:
        for task in list(ui.tasks): task.cancel()
        await asyncio.gather(*ui.tasks,return_exceptions=True)
        await backend.close()
        if keyboard: keyboard.close()
        if fb: fb.close()
        store.db.close()


def main():
    parser=argparse.ArgumentParser(description='MeshCore for Cardputer Zero')
    parser.add_argument('--data',help='Override local data directory')
    parser.add_argument('--screenshot',help='Render the inbox to a PNG and exit without hardware')
    parser.add_argument('--demo',action='store_true',help='Insert preview data; use a disposable --data directory')
    parser.add_argument('--duration',type=float,help='Exit after this many seconds (device smoke test)')
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    asyncio.run(run(args))


if __name__=='__main__': main()
