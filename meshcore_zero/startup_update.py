"""One quiet, bounded release check per launch; never delay radio or input."""
import asyncio
import json
import sys


async def available_release():
    process = None
    try:
        # Isolate urllib/DNS in a short-lived child so even a stalled resolver
        # cannot hold up app exit or leave a background checker running.
        process = await asyncio.create_subprocess_exec(
            sys.executable, '-m', 'meshcore_zero.update', '--startup-check',
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL)
        output, _ = await asyncio.wait_for(process.communicate(), 7)
        if process.returncode == 0:
            return json.loads(output)
    except (OSError, ValueError, asyncio.TimeoutError):
        pass  # Offline, current, or unavailable GitHub: open normally.
    finally:
        if process and process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.communicate()
    return None


async def check_at_startup(ui):
    release = await available_release()
    if not release:
        return
    while ui.running and ui.launch_state:
        await asyncio.sleep(.1)
    # An explicit Settings update takes priority over this automatic check.
    if ui.running and ui.screen != 'update':
        ui.startup_release = release
        ui.startup_update_choice = 0
