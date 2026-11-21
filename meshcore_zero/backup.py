"""Authenticated, password-encrypted logical backups. No private data in logs."""
import datetime
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
from nacl import pwhash
from nacl.secret import SecretBox
from nacl.exceptions import CryptoError
from . import __version__
from .identity_keys import stored_key,public_key

MAGIC=b'MCZBACKUP\x01'
MAX_SIZE=16*1024*1024
MEMORY=16*1024*1024
TABLES={
 'settings':['key','value'],
 'chats':['id','name','kind','secret','unread','muted','scope'],
 'messages':['id','chat','sender','text','timestamp','status','token','tx_hash','heard_at','heard_hops'],
 'nodes':['key','data'],
}

def root_for(store):return Path(store.db.execute('PRAGMA database_list').fetchone()[2]).parent

def derive(password,salt):
    if not isinstance(password,str) or not 8<=len(password)<=128:raise ValueError('Use a password of 8–128 characters')
    return pwhash.argon2id.kdf(SecretBox.KEY_SIZE,password.encode(),salt,opslimit=3,memlimit=MEMORY)

def snapshot(directory):
    directory=Path(directory);path=directory/'meshcore.sqlite'
    conn=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True);conn.row_factory=sqlite3.Row
    try:
        conn.execute('BEGIN')
        estimated=0
        for table,columns in TABLES.items():
            expression='+'.join('COALESCE(length(CAST('+column+' AS BLOB)),0)' for column in columns)
            count,size=conn.execute('SELECT COUNT(*),COALESCE(SUM('+expression+'),0) FROM '+table).fetchone()
            if count>100000:raise ValueError('Backup exceeds the 100,000 rows per table safety limit')
            estimated+=size
        if estimated>MAX_SIZE:raise ValueError('Backup exceeds the 16 MiB safety limit')
        result={table:[dict(r) for r in conn.execute('SELECT '+','.join(columns)+' FROM '+table)] for table,columns in TABLES.items()}
        credentials=[]
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='repeater_passwords'").fetchone():
            rows=list(conn.execute('SELECT public_key,encrypted FROM repeater_passwords'))
            if rows:
                fd=os.open(directory/'repeater-password.key',os.O_RDONLY|os.O_NOFOLLOW)
                with os.fdopen(fd,'rb') as f:key=f.read(33)
                box=SecretBox(key)
                for row in rows:
                    try:password=box.decrypt(bytes(row['encrypted'])).decode()
                    except (CryptoError,UnicodeError):raise ValueError('Saved repeater passwords could not be backed up') from None
                    credentials.append({'public_key':row['public_key'],'password':password})
        result['credentials']=credentials
        result['format']=1;result['app_version']=__version__
        result['created']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        validate(result)
        return result
    finally:conn.close()

def validate(data):
    def fail():raise ValueError('Invalid or unsupported MeshCore backup')
    if not isinstance(data,dict) or data.get('format')!=1:fail()
    if set(data)!={'format','app_version','created','credentials',*TABLES}:fail()
    for table,columns in TABLES.items():
        rows=data[table]
        if not isinstance(rows,list) or len(rows)>100000:fail()
        for row in rows:
            if not isinstance(row,dict) or set(row)!=set(columns):fail()
            if any(not isinstance(v,(str,int,type(None))) or isinstance(v,bool) for v in row.values()):fail()
            if any(isinstance(v,int) and not -(2**63)<=v<2**63 for v in row.values()):fail()
            if any(isinstance(v,str) and len(v)>1024*1024 for v in row.values()):fail()
    settings={r['key']:r['value'] for r in data['settings']}
    if len(settings)!=len(data['settings']) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in settings.items()):fail()
    if settings.get('identity'):stored_key(settings['identity'])
    if settings.get('identity_backup'):stored_key(settings['identity_backup'])
    from .regions import PRESETS
    if settings.get('region','US') not in PRESETS:fail()
    for k,v in settings.items():
        if k.startswith('coding_rate_') and v not in ('5','6','7','8'):fail()
    if sum(r['kind']=='channel' for r in data['chats'])>32:fail()
    ids=set()
    for r in data['chats']:
        if not isinstance(r['id'],str) or r['id'] in ids or not isinstance(r['name'],str):fail()
        ids.add(r['id'])
        if r['kind']=='channel':
            if r['id'].startswith('private:'):
                from .channels import validate_private
                if not re.fullmatch(r'private:[0-9a-f]{32}',r['id']):fail()
                try:validate_private(r['name'],bytes.fromhex(r['secret']))
                except (ValueError,TypeError):fail()
            elif r['id']!='public' and not re.fullmatch(r'#[a-z0-9][a-z0-9_-]{0,29}',r['id']):fail()
            if not isinstance(r['secret'],str) or not re.fullmatch('[0-9a-fA-F]{32}',r['secret']):fail()
        elif r['kind']=='dm':
            if not re.fullmatch('[0-9a-fA-F]{64}',r['id']) or r['scope'] is not None:fail()
        else:fail()
        if r['muted'] not in (0,1) or not isinstance(r['unread'],int) or r['unread']<0:fail()
        if r['scope'] is not None and (not isinstance(r['scope'],str) or not re.fullmatch('[a-z0-9][a-z0-9_-]{0,29}',r['scope'])):fail()
    channels=[r for r in data['chats'] if r['kind']=='channel']
    for r in channels:
        if r['id'].startswith('private:'):
            if any(other['id']!=r['id'] and (other['secret'].lower()==r['secret'].lower() or other['name'].casefold()==r['name'].casefold()) for other in channels):fail()
    mids=set();tokens=set()
    for r in data['messages']:
        if not isinstance(r['id'],int) or r['id']<=0 or r['id'] in mids or r['chat'] not in ids:fail()
        mids.add(r['id'])
        if not isinstance(r['sender'],str) or not isinstance(r['text'],str) or not isinstance(r['timestamp'],int):fail()
        if r['status'] not in ('received','sending','sent','delivered','failed','unconfirmed','interrupted'):fail()
        if r['token'] is not None:
            if not isinstance(r['token'],str) or r['token'] in tokens:fail()
            tokens.add(r['token'])
        if r['tx_hash'] is not None and not isinstance(r['tx_hash'],str):fail()
        for k in ('heard_at','heard_hops'):
            if r[k] is not None and not isinstance(r[k],int):fail()
    nodekeys=set()
    for r in data['nodes']:
        if not isinstance(r['key'],str) or not re.fullmatch('[0-9a-fA-F]{64}',r['key']) or r['key'] in nodekeys or not isinstance(r['data'],str):fail()
        nodekeys.add(r['key'])
        try:node=json.loads(r['data'])
        except ValueError:fail()
        if not isinstance(node,dict) or node.get('public_key')!=r['key']:fail()
        from openhop_core.companion.models import Contact
        try:Contact.from_dict(node)
        except (TypeError,ValueError,OverflowError):fail()
    credentials=data['credentials'];seen=set()
    if not isinstance(credentials,list) or len(credentials)>10000:fail()
    for r in credentials:
        if not isinstance(r,dict) or set(r)!={'public_key','password'}:fail()
        key=r['public_key'];password=r['password']
        if not isinstance(key,str) or not re.fullmatch('[0-9a-fA-F]{64}',key) or key in seen:fail()
        if not isinstance(password,str) or len(password)>1024:fail()
        seen.add(key)
    return data

def export(directory,password,prefix='meshcore-backup'):
    data=snapshot(directory)
    raw=json.dumps(data,separators=(',',':'),ensure_ascii=False).encode()
    if len(raw)>MAX_SIZE:raise ValueError('Backup exceeds the 16 MiB safety limit')
    salt=os.urandom(pwhash.argon2id.SALTBYTES)
    encrypted=MAGIC+salt+bytes(SecretBox(derive(password,salt)).encrypt(raw))
    target=Path(directory)/'backups';target.mkdir(mode=0o700,exist_ok=True)
    if target.is_symlink():raise ValueError('Backup directory must not be a symlink')
    os.chmod(target,0o700)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    destination=target/(prefix+'-'+stamp+'.mczb')
    fd,tmp=tempfile.mkstemp(prefix='.backup-',dir=target)
    try:
        with os.fdopen(fd,'wb') as f:f.write(encrypted);f.flush();os.fsync(f.fileno())
        os.replace(tmp,destination)
        directory_fd=os.open(target,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory_fd)
        finally:os.close(directory_fd)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return destination

def read(path,password):
    fd=os.open(Path(path).expanduser(),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):raise ValueError('Choose a regular backup file')
        blob=f.read(MAX_SIZE+1025)
    if len(blob)>MAX_SIZE+1024 or not blob.startswith(MAGIC):raise ValueError('Invalid or unsupported MeshCore backup')
    offset=len(MAGIC);salt=blob[offset:offset+16]
    if len(salt)!=16:raise ValueError('Invalid or unsupported MeshCore backup')
    try:raw=SecretBox(derive(password,salt)).decrypt(blob[offset+16:])
    except CryptoError:raise ValueError('Wrong password or damaged backup') from None
    try:data=json.loads(raw)
    except (ValueError,UnicodeError):raise ValueError('Invalid or unsupported MeshCore backup') from None
    return validate(data)

def summary(data):
    settings={r['key']:r['value'] for r in data['settings']}
    return {'public_key':public_key(stored_key(settings['identity'])) if settings.get('identity') else 'Not initialized','channels':sum(r['kind']=='channel' for r in data['chats']),'messages':len(data['messages']),'contacts':len(data['nodes']),'passwords':len(data['credentials'])}

def apply_restore(store,data,password):
    """Call only after radio shutdown; atomically replace database contents."""
    validate(data)
    from .repeater_passwords import RepeaterPasswords
    saved=RepeaterPasswords(store)
    # Do all file/crypto work before touching the live transaction. Keep the
    # current local credential key so a failed restore leaves old rows usable.
    encrypted=[]
    if data['credentials']:
        box=saved.box(create=True)
        encrypted=[(r['public_key'],bytes(box.encrypt(r['password'].encode()))) for r in data['credentials']]
    recovery=export(root_for(store),password,prefix='before-restore')
    with store.db:
        for table in TABLES:store.db.execute('DELETE FROM '+table)
        store.db.execute('DELETE FROM repeater_passwords')
        for table,columns in TABLES.items():
            store.db.executemany('INSERT INTO '+table+' ('+','.join(columns)+') VALUES ('+','.join('?' for _ in columns)+')',[[r[c] for c in columns] for r in data[table]])
        store.db.executemany('INSERT INTO repeater_passwords VALUES (?,?)',encrypted)
        store.db.execute("INSERT OR REPLACE INTO settings VALUES('channels_initialized','1')")
        store.db.execute("UPDATE messages SET status='interrupted' WHERE status='sending'")
    return recovery
