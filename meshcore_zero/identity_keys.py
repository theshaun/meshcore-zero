"""MeshCore firmware identity interchange. Never log or display private keys."""
import hashlib
import os
from pathlib import Path
import re
import stat
import tempfile
from nacl.bindings import crypto_sign_ed25519_pk_to_curve25519,crypto_scalarmult_base


def validate(raw):
    from openhop_core.protocol.identity import LocalIdentity
    if len(raw) not in (32,64):raise ValueError('Invalid stored identity')
    if len(raw)==64:
        from nacl.signing import SigningKey
        if SigningKey(raw[:32]).verify_key.encode()==raw[32:]:
            raise ValueError('Expected firmware expanded key, not seed/public pair')
    try:
        identity=LocalIdentity(raw)
        public=identity.get_public_key()
        if public[0] in (0,255):raise ValueError()
        if crypto_sign_ed25519_pk_to_curve25519(public)!=crypto_scalarmult_base(identity.get_private_key()):
            raise ValueError()
        signature=identity.sign(b'MeshCore identity validation')
        identity.verify_key.verify(b'MeshCore identity validation',signature)
        return identity
    except Exception:
        raise ValueError('Invalid MeshCore identity key') from None


def stored_key(value):
    if value is None:raise ValueError('Identity not ready · wait for radio')
    try:raw=bytes.fromhex(value)
    except (ValueError,TypeError):raise ValueError('Invalid stored identity') from None
    validate(raw)
    return raw


def parse_firmware(text):
    text=re.sub(r'\s+','',text)
    if not re.fullmatch('[0-9a-fA-F]{128}',text):
        raise ValueError('Firmware key needs 128 hexadecimal characters')
    raw=bytes.fromhex(text);validate(raw)
    return raw


def firmware_key(raw):
    validate(raw)
    if len(raw)==64:return raw
    expanded=bytearray(hashlib.sha512(raw).digest())
    expanded[0]&=248;expanded[31]&=63;expanded[31]|=64
    return bytes(expanded)


def public_key(raw):
    return validate(raw).get_public_key().hex()


def read_key_file(path):
    fd=os.open(Path(path).expanduser(),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):raise ValueError('Choose a regular key text file')
        data=f.read(4097)
    if len(data)>4096:raise ValueError('Key file is too large')
    try:text=data.decode('utf-8-sig')
    except UnicodeError:raise ValueError('Choose a hexadecimal key text file') from None
    return parse_firmware(text)


def export_key(store):
    raw=stored_key(store.get('identity'))
    directory=Path(store.db.execute('PRAGMA database_list').fetchone()[2]).parent
    destination=directory/'identity-export.txt'
    fd,tmp=tempfile.mkstemp(prefix='.identity-export-',dir=directory)
    try:
        with os.fdopen(fd,'w') as f:
            f.write(firmware_key(raw).hex()+'\n');f.flush();os.fsync(f.fileno())
        os.replace(tmp,destination)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    return destination


def replace_identity(store,raw):
    validate(raw)
    previous=store.get('identity')
    if previous and public_key(stored_key(previous))==public_key(raw):return False
    with store.db:
        if previous:store.db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('identity_backup',previous))
        store.db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',('identity',firmware_key(raw).hex()))
    return True
