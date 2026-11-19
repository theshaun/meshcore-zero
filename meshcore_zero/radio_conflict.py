"""Check CAP ownership before radio startup; never stop MeshZero before any MeshCore hardware initialization."""
import asyncio
import logging

log=logging.getLogger(__name__)
SYSTEMCTL='/usr/bin/systemctl'
UNIT='meshzero.service'


class ServiceError(RuntimeError):
    pass


async def command(*args, timeout=5):
    try:
        process=await asyncio.create_subprocess_exec(*args,stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    except OSError as exc:
        raise ServiceError('Cannot check the MeshZero service.') from exc
    try:
        stdout,stderr=await asyncio.wait_for(process.communicate(),timeout)
    except (asyncio.TimeoutError,asyncio.CancelledError) as exc:
        if process.returncode is None:
            try: process.kill()
            except ProcessLookupError: pass
        await process.communicate()
        if isinstance(exc,asyncio.CancelledError): raise
        raise ServiceError('MeshZero service check timed out.') from exc
    return process.returncode,stdout.decode(errors='replace')


async def is_running():
    code,output=await command(SYSTEMCTL,'show',UNIT,'--no-pager',
        '--property=LoadState,ActiveState,MainPID')
    fields=dict(line.split('=',1) for line in output.splitlines() if '=' in line)
    if fields.get('LoadState')=='not-found': return False
    if code or fields.get('LoadState') not in ('loaded','masked'):
        raise ServiceError('Cannot check the MeshZero service.')
    state=fields.get('ActiveState')
    try: pid=int(fields['MainPID'])
    except (KeyError,ValueError) as exc:
        raise ServiceError('Cannot verify the MeshZero service.') from exc
    if state not in ('inactive','failed','active','activating','deactivating','reloading','refreshing'):
        raise ServiceError('Cannot verify the MeshZero service.')
    return pid!=0 or state not in ('inactive','failed')


async def start_radio(ui,backend,check=is_running):
    try:
        while ui.running:
            ui.launch_state='checking'
            if await check():
                ui.launch_ack.clear()
                ui.launch_state='conflict'
                await ui.launch_ack.wait()
                continue  # Okay rechecks; never stops another service.
            # Recheck immediately before hardware initialization.
            if await check(): continue
            if not ui.running: return
            ui.launch_state=''
            await backend.start()
            return
    except ServiceError as exc:
        log.warning('Radio conflict check: %s',exc)
        ui.launch_state='error'
        ui.launch_error=str(exc)
        backend.error=str(exc)
        backend.state='Radio not started'
    except Exception:
        log.exception('Radio service check failed')
        ui.launch_state='error'
        ui.launch_error='Cannot check the radio service.'
        backend.error=ui.launch_error
        backend.state='Radio not started'
