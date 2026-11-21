"""MeshCore's 16-byte group keys and local channel classification."""
import base64
import binascii
import hashlib
import re
import uuid

PUBLIC_KEY='8b3387e9c5cdea6ac9e5edbaa115cd72'

def private_name(value):
    value=value.strip()
    try:valid=1<=len(value.encode('utf-8'))<=32
    except UnicodeError:valid=False
    if not valid or any(not c.isprintable() and c!='\u200d' for c in value):raise ValueError('Name must be 1–32 UTF-8 bytes')
    if value.startswith('#') or value.casefold()=='public':raise ValueError('Private name cannot be Public or start with #')
    return value

def parse_key(text):
    text=''.join(text.split())
    try:
        if re.fullmatch('[0-9a-fA-F]{32}',text):raw=bytes.fromhex(text)
        else:raw=base64.b64decode(text+'='*(-len(text)%4),altchars=b'-_',validate=True)
    except (ValueError,binascii.Error):raise ValueError('Use a 16-byte key: 32 hex or Base64') from None
    if len(raw)!=16:raise ValueError('Use a 16-byte key: 32 hex or Base64')
    if raw==bytes(16) or raw.hex()==PUBLIC_KEY:raise ValueError('Use a private key, not the Public or zero key')
    return raw

def channel_type(chat):
    if chat['kind']=='dm':return 'dm'
    if chat['id'].startswith('private:'):return 'private'
    return 'public' if chat['id']=='public' else 'hashtag'

def validate_private(name,raw):
    name=private_name(name)
    if len(raw)!=16 or raw==bytes(16) or raw.hex()==PUBLIC_KEY:raise ValueError('Invalid private channel key')
    if raw==hashlib.sha256(('#'+name.lower()).encode()).digest()[:16]:raise ValueError('A hashtag-derived key is public, not private')
    return name

def join_private(store,name,text):
    raw=parse_key(text);name=validate_private(name,raw)
    rows=list(store.db.execute("SELECT * FROM chats WHERE kind='channel'"))
    for row in rows:
        if row['secret']==raw.hex():
            if channel_type(row)=='private':return row['id']
            raise ValueError('Key belongs to an existing public channel')
    if any(row['name'].casefold()==name.casefold() for row in rows):raise ValueError('Channel name already used · choose another')
    if len(rows)>=32:raise ValueError('Channel limit reached (32)')
    cid='private:'+uuid.uuid4().hex
    with store.db:store.db.execute("INSERT INTO chats(id,name,kind,secret) VALUES (?,?,'channel',?)",(cid,name,raw.hex()))
    return cid
