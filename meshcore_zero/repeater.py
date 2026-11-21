"""Read-only, authenticated repeater status; credentials never enter storage."""
import asyncio
from datetime import datetime, timezone


def battery_estimate(mv):
    # An estimate only: MeshCore reports voltage, not chemistry or charge state.
    if not isinstance(mv,(int,float)) or not 3000 <= mv <= 4350:
        return None
    curve=((3000,0),(3300,5),(3500,10),(3600,20),(3700,35),(3800,55),(3900,75),(4000,85),(4100,95),(4200,100),(4350,100))
    for (a,x),(b,y) in zip(curve,curve[1:]):
        if a <= mv <= b:return round(x+(mv-a)*(y-x)/(b-a))


def status_lines(stats, clock=None):
    mv=stats.get('batt_milli_volts')
    pct=battery_estimate(mv)
    battery=(f'{mv/1000:.2f} V' if isinstance(mv,(int,float)) and mv>0 else 'Unavailable')
    if pct is not None:battery=f'~{pct}% · '+battery
    secs=stats.get('total_up_time_secs')
    uptime='Unavailable' if secs is None else f'{int(secs)//86400}d {int(secs)//3600%24}h {int(secs)//60%60}m'
    noise=stats.get('noise_floor');snr=stats.get('last_snr')
    try:stamp=datetime.fromtimestamp(clock,timezone.utc).strftime('%H:%M:%S · %Y-%m-%d UTC') if clock else 'Unavailable'
    except (ValueError,OverflowError,OSError):stamp='Unavailable'
    return [('Battery*',battery),('Uptime',uptime),('Noise floor','Unavailable' if noise is None else f'{noise:g} dBm'),('Last SNR','Unavailable' if snr is None else f'{snr:g} dB'),('Clock',stamp)]


async def repeater_clock(engine, key):
    from openhop_core.protocol.constants import ANON_REQ_TYPE_BASIC
    received={};ready=asyncio.Event();tag=None
    def response(raw_tag, data, parsed=None, request_type=None):
        nonlocal tag
        value=int.from_bytes(raw_tag,'little')
        if isinstance(parsed,dict) and parsed.get('type')=='basic':
            received[value]=parsed.get('clock')
            if value==tag:ready.set()
    engine.on_binary_response(response)
    try:
        sent=await engine.send_anon_req(key,bytes([ANON_REQ_TYPE_BASIC]),timeout_seconds=12)
        if not sent.success:return None
        tag=sent.expected_ack
        if tag not in received:
            await asyncio.wait_for(ready.wait(),12)
        return received.get(tag)
    except asyncio.TimeoutError:
        return None
    finally:
        engine.remove_push_callback('binary_response',response)


async def request_status(backend, public_key, password):
    if not backend or not backend.engine or not backend.engine.is_running:
        raise ValueError('Radio offline')
    if len(password.encode())>15:
        raise ValueError('Password limit: 15 UTF-8 bytes')
    key=bytes.fromhex(public_key)
    async with backend.send_lock:
        try:
            login=await backend.engine.send_login(key,password)
            password=''
            if not login.get('success'):
                raise ValueError('Login failed · check password / reachability')
            result=await backend.engine.send_status_request(key,timeout=20)
            if not result.get('success'):
                raise ValueError('No status reply · retry when reachable')
            stats=result.get('stats',{})
            try:
                clock=await repeater_clock(backend.engine,key)
            except Exception:
                clock=None  # Older repeaters may not support the basic clock query.
            return stats,clock
        finally:
            password=''
