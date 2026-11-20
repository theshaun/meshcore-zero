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
    startup=None
    from .screen_idle import ScreenIdle
    from .sound import MessageSound
    screen_idle=ScreenIdle()
    sound=MessageSound(store)
    input_ready=asyncio.Event()
    backend=Backend(store,ui.notice,sound.received)
    ui.backend=backend
    loop=asyncio.get_running_loop()
    for sig in (signal.SIGTERM,signal.SIGINT):
        loop.add_signal_handler(sig,lambda:setattr(ui,'running',False))
    try:
        fb=Framebuffer()
        keyboard=Keyboard()
        loop.add_reader(keyboard.fd,input_ready.set)
        await asyncio.to_thread(screen_idle.tick)
        screen_task=asyncio.create_task(screen_idle.run())
        ui.tasks.add(screen_task)
        screen_task.add_done_callback(ui.tasks.discard)
        ui.launch_state='checking'
        fb.write(ui.render())  # Show preflight before touching the radio.
        from .radio_conflict import start_radio
        startup=asyncio.create_task(start_radio(ui,backend))
        from .startup_update import check_at_startup
        update_task=asyncio.create_task(check_at_startup(ui))
        ui.tasks.add(update_task)
        update_task.add_done_callback(ui.tasks.discard)
        from .startup_advert import announce_after_checks
        advert_task=asyncio.create_task(announce_after_checks(ui,backend,startup,update_task))
        ui.tasks.add(advert_task)
        advert_task.add_done_callback(ui.tasks.discard)
        from .battery import monitor
        battery_task=asyncio.create_task(monitor(ui))
        ui.tasks.add(battery_task)
        battery_task.add_done_callback(ui.tasks.discard)
        previous=None
        started=loop.time()
        while ui.running and (not args.duration or loop.time()-started<args.duration):
            input_ready.clear()
            keys=keyboard.read()
            if keys and await screen_idle.activity():
                keys=[]
                previous=None  # Force the current image through the LCD on wake.
            for key in keys:
                await ui.key(key)
            key=ui.render_key()
            if key!=previous:
                fb.write(ui.render())
                previous=ui.render_key()
            try:
                await asyncio.wait_for(input_ready.wait(),timeout=.05)
            except asyncio.TimeoutError:
                pass
    finally:
        if startup and not startup.done(): startup.cancel()
        if startup: await asyncio.gather(startup,return_exceptions=True)
        for task in list(ui.tasks): task.cancel()
        await asyncio.gather(*ui.tasks,return_exceptions=True)
        await backend.close()
        await sound.close()
        await screen_idle.close()
        if keyboard:
            loop.remove_reader(keyboard.fd)
            keyboard.close()
        if fb: fb.close()
        store.db.close()
        ui.updater.cleanup()
    if ui.restart_requested:
        command=['meshcore-zero']
        if args.data:command+=['--data',args.data]
        os.execv('/usr/share/APPLaunch/bin/meshcore-zero',command)


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
