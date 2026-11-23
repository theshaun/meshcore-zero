"""Validated MeshCore community catalog; offline first, never retune on refresh."""
import asyncio
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time
from urllib.request import Request,urlopen

API='https://api.meshcore.nz/api/v1/config'
MAX_BYTES=256*1024
CACHE_KEY='radio_presets'
TIME_KEY='radio_presets_updated'
PROFILE_PREFIX='radio_profile_'
TITLE_KEYS={
 'Australia':'AU_WIDE','Australia (Narrow)':'AU','Australia (Mid)':'AU_MID',
 'Australia: SA, WA':'AU_SA_WA','Australia: QLD':'AU_QLD','Brazil':'BR',
 'Canada':'CA','Costa Rica':'CR','EU/UK (Narrow)':'UK','EU/UK (Deprecated)':'EU_LONG',
 'Czech Republic (Narrow)':'CZ','EU 433MHz (Long Range)':'EU_433_LONG',
 'EU 433MHz (Narrow)':'EU_433_NARROW','Hungary':'HU','Netherlands':'NL',
 'Netherlands (Limburg)':'NL_LIMBURG','New Zealand (Narrow)':'NZ',
 'New Zealand (Gisborne)':'NZ_GISBORNE','Portugal 433':'PT_433','Portugal 868':'PT',
 'Slovakia':'SK','Switzerland':'CH','Thailand':'TH','USA':'US',
 'USA - Southern California':'US_SOCAL','Vietnam (Narrow)':'VN','Vietnam (Deprecated)':'VN_LONG'}


def title_key(title):
    return TITLE_KEYS.get(title,'MC_'+hashlib.sha256(title.casefold().encode()).hexdigest()[:16].upper())


def default_power(key,frequency):
    if key in ('JP','TH','VN','VN_LONG'):return 13
    return 10 if frequency<500000000 else 14 if frequency<870000000 else 20


def validate_entry(entry):
    if not isinstance(entry,dict) or set(entry)!={'id','title','radio','path_bytes'}:raise ValueError('Invalid radio preset')
    key,title,radio,size=(entry[k] for k in ('id','title','radio','path_bytes'))
    if not isinstance(key,str) or not re.fullmatch('[A-Z][A-Z0-9_]{0,39}',key):raise ValueError('Invalid preset ID')
    if not isinstance(title,str) or not 1<=len(title)<=72 or any(not c.isprintable() for c in title):raise ValueError('Invalid preset title')
    fields={'frequency','bandwidth','spreading_factor','coding_rate','tx_power'}
    if not isinstance(radio,dict) or set(radio)!=fields or any(type(v)!=int for v in radio.values()):raise ValueError('Invalid radio parameters')
    if not 400000000<=radio['frequency']<=960000000 or radio['bandwidth'] not in (15625,31250,62500,125000,250000,500000):raise ValueError('Unsupported frequency / bandwidth')
    if not 5<=radio['spreading_factor']<=12 or radio['coding_rate'] not in (5,6,7,8):raise ValueError('Unsupported SF / coding rate')
    if radio['tx_power']!=default_power(key,radio['frequency']):raise ValueError('Invalid preset power')
    if type(size)!=int or size not in (1,2,3):raise ValueError('Invalid path hash size')
    return entry


def validate_entries(entries):
    if not isinstance(entries,list) or not 1<=len(entries)<=256:raise ValueError('Invalid preset list')
    seen=set()
    for entry in entries:
        validate_entry(entry)
        if entry['id']!=title_key(entry['title']) or entry['id'] in seen:raise ValueError('Duplicate / invalid preset ID')
        seen.add(entry['id'])
    return entries


def parse_api(data):
    raw=data['config']['suggested_radio_settings']['entries']
    if not isinstance(raw,list) or not 1<=len(raw)<=256:raise ValueError('Invalid preset list')
    entries=[]
    for row in raw:
        title=row['title'];key=title_key(title)
        def number(name,multiplier=1):
            value=float(row[name])*multiplier
            if not math.isfinite(value) or value!=round(value):raise ValueError('Invalid preset number')
            return int(value)
        frequency=number('frequency',1000000)
        radio=dict(frequency=frequency,bandwidth=number('bandwidth',1000),
                   spreading_factor=number('spreading_factor'),coding_rate=number('coding_rate'),
                   tx_power=default_power(key,frequency))
        size=row.get('network_settings',{}).get('path_hash_size',1)
        entries.append(dict(id=key,title=title,radio=radio,path_bytes=size))
    return validate_entries(entries)


def bundled_entries():
    return validate_entries(json.loads(Path(__file__).with_name('bundled_presets.json').read_text())['entries'])


def catalog(store=None,settings=None):
    from .regions import PRESETS,NAMES,PATH_BYTES
    result={key:dict(id=key,title=NAMES[key],radio=dict(radio),path_bytes=PATH_BYTES.get(key,1)) for key,radio in PRESETS.items()}
    for row in bundled_entries():result[row['id']]=row
    get=settings.get if settings is not None else store.get if store else lambda key,default=None:default
    cached=get(CACHE_KEY)
    if cached:
        try:
            for row in validate_entries(json.loads(cached)):result[row['id']]=row
        except (ValueError,TypeError,KeyError):pass  # Corrupt cache never prevents offline startup.
    rows=settings.items() if settings is not None else store.db.execute('SELECT key,value FROM settings') if store else ()
    for key,value in rows:
        if key.startswith(PROFILE_PREFIX):
            try:
                row=validate_entry(json.loads(value))
                if key!=PROFILE_PREFIX+row['id']:raise ValueError('Invalid saved profile')
                result.setdefault(row['id'],row)  # Retain a selected/removed upstream profile.
            except (ValueError,TypeError,KeyError):continue
    return result


def selected_profile(store,region):
    from .regions import PRESETS,NAMES,PATH_BYTES
    saved=store.get(PROFILE_PREFIX+region)
    if saved:
        row=validate_entry(json.loads(saved))
        if row['id']!=region:raise ValueError('Invalid selected profile')
        return row
    # Existing installations retain their exact legacy values, independent of refresh.
    if region in PRESETS:return dict(id=region,title=NAMES[region],radio=dict(PRESETS[region]),path_bytes=PATH_BYTES.get(region,1))
    raise ValueError('Select this radio preset again')


def supported(entry):return 868000000<=entry['radio']['frequency']<=923000000


def select_profile(store,entry):
    validate_entry(entry)
    if not supported(entry):raise ValueError('This preset needs a different radio CAP')
    with store.db:
        store.db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(PROFILE_PREFIX+entry['id'],json.dumps(entry,separators=(',',':'))))
        store.db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('region',entry['id']))


def fetch_entries():
    request=Request(API,headers={'User-Agent':'MeshCore-Zero-presets','Accept':'application/json'})
    with urlopen(request,timeout=5) as response:
        if response.url!=API:raise ValueError('Unexpected preset redirect')
        raw=response.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:raise ValueError('Preset response too large')
    return parse_api(json.loads(raw))


async def download_entries():
    process=None
    try:
        process=await asyncio.create_subprocess_exec(sys.executable,'-m','meshcore_zero.preset_catalog','--fetch',
            stdin=asyncio.subprocess.DEVNULL,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
        output,_=await asyncio.wait_for(process.communicate(),7)
        if process.returncode==0 and len(output)<=MAX_BYTES:return validate_entries(json.loads(output))
    except (OSError,ValueError,TypeError,KeyError,asyncio.TimeoutError):pass
    finally:
        if process and process.returncode is None:
            try:process.kill()
            except ProcessLookupError:pass
            await process.communicate()
    return None


async def refresh(ui,manual=False):
    if ui.presets_busy:
        if manual:ui.notice('Refreshing radio presets…')
        return
    try:age=time.time()-float(ui.store.get(TIME_KEY,'0'))
    except ValueError:age=86400
    if not manual and 0<=age<86400:return
    ui.presets_busy=True
    if manual:ui.notice('Refreshing radio presets…')
    try:
        rows=await download_entries()
        if rows:
            with ui.store.db:
                ui.store.db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(CACHE_KEY,json.dumps(rows,separators=(',',':'))))
                ui.store.db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(TIME_KEY,str(time.time())))
            if manual and ui.screen=='regions':
                old=list(ui.region_choices())[min(ui.selected,len(ui.region_choices())-1)]
                ui.region_catalog=catalog(ui.store)
                keys=list(ui.region_catalog);ui.selected=keys.index(old) if old in keys else 0
            if manual:ui.notice('Radio presets updated')
        elif manual:ui.notice('Offline / unavailable · kept saved presets')
    finally:ui.presets_busy=False


if __name__=='__main__':
    try:print(json.dumps(fetch_entries(),separators=(',',':')))
    except Exception:sys.exit(1)
