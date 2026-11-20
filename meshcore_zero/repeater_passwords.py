"""Opt-in local repeater credentials, encrypted with a private device-local key."""
import os
from pathlib import Path
from nacl.secret import SecretBox
from nacl.exceptions import CryptoError

class RepeaterPasswords:
    def __init__(self,store):
        self.db=store.db
        directory=Path(self.db.execute('PRAGMA database_list').fetchone()[2]).parent
        self.key_path=directory/'repeater-password.key'
        self.db.execute('CREATE TABLE IF NOT EXISTS repeater_passwords(public_key TEXT PRIMARY KEY, encrypted BLOB NOT NULL)')
        self.db.commit()

    def box(self,create=False):
        if create and not self.key_path.exists():
            try:
                fd=os.open(self.key_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(fd,'wb') as f:
                    f.write(os.urandom(SecretBox.KEY_SIZE));f.flush();os.fsync(f.fileno())
        fd=os.open(self.key_path,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as f:
            os.fchmod(f.fileno(),0o600)
            key=f.read(SecretBox.KEY_SIZE+1)
        return SecretBox(key)

    def get(self,public_key):
        row=self.db.execute('SELECT encrypted FROM repeater_passwords WHERE public_key=?',(public_key,)).fetchone()
        if not row:return None
        try:
            return self.box().decrypt(bytes(row[0])).decode('utf-8')
        except (OSError,ValueError,CryptoError,UnicodeError):
            return None

    def save(self,public_key,password):
        encrypted=self.box(create=True).encrypt(password.encode('utf-8'))
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO repeater_passwords VALUES(?,?)',(public_key,bytes(encrypted)))

    def forget(self,public_key):
        with self.db:self.db.execute('DELETE FROM repeater_passwords WHERE public_key=?',(public_key,))
