"""One flood advert after radio and startup-update checks are complete."""
import asyncio
import logging

async def announce_after_checks(ui, backend, radio_task, update_task):
    await asyncio.gather(radio_task,update_task)
    while ui.running and (ui.startup_release or ui.screen=='update'):
        await asyncio.sleep(.1)
    if not ui.running or ui.launch_state or not backend.engine or not backend.engine.is_running:
        return
    try:
        sent=await backend.announce()
        logging.getLogger(__name__).info('Startup flood advert %s', 'sent' if sent else 'failed')
    except Exception:
        logging.getLogger(__name__).warning('Startup advert failed',exc_info=True)
        ui.notice('Startup announcement failed · retry in Settings')
