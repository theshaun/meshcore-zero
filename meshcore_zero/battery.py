"""Read the kernel fuel gauge away from the keyboard/rendering event loop."""
import asyncio
from pathlib import Path


def read_capacity(root=Path('/sys/class/power_supply')):
    try:
        supplies=sorted(root.iterdir())
    except OSError:
        return None
    for supply in supplies:
        try:
            if (supply/'type').read_text().strip()!='Battery': continue
            capacity=int((supply/'capacity').read_text().strip())
            if 0<=capacity<=100: return capacity
        except (OSError,ValueError):
            continue
    return None


async def monitor(ui):
    while True:
        ui.battery=await asyncio.to_thread(read_capacity)
        await asyncio.sleep(15)
