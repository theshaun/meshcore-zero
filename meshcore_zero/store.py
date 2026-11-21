"""Transactional local history. Only the radio worker and UI's event loop use this."""
import hashlib
import os
import re
import sqlite3
import time
from pathlib import Path

from .channels import PUBLIC_KEY
from .regions import PRESETS


def radio_config(store, region=None):
    region = region or store.get('region', 'US')
    if region not in PRESETS:
        raise ValueError('Unknown radio region')
    config = dict(PRESETS[region])
    coding_rate = int(store.get('coding_rate_' + region, config['coding_rate']))
    if coding_rate not in (5, 6, 7, 8):
        raise ValueError('Coding rate must be 4/5, 4/6, 4/7 or 4/8')
    config['coding_rate'] = coding_rate
    return config


class Store:
    def __init__(self, directory):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(directory, 0o700)
        self.db = sqlite3.connect(directory / "meshcore.sqlite")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
          PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
          CREATE TABLE IF NOT EXISTS chats(id TEXT PRIMARY KEY, name TEXT, kind TEXT, secret TEXT, unread INTEGER DEFAULT 0);
          CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, chat TEXT, sender TEXT, text TEXT, timestamp INTEGER, status TEXT, token TEXT UNIQUE, tx_hash TEXT, heard_at INTEGER, heard_hops INTEGER);
          CREATE TABLE IF NOT EXISTS nodes(key TEXT PRIMARY KEY, data TEXT);
          CREATE INDEX IF NOT EXISTS history ON messages(chat,id);
        """)
        chat_columns={row[1] for row in self.db.execute('PRAGMA table_info(chats)')}
        if 'muted' not in chat_columns:self.db.execute('ALTER TABLE chats ADD COLUMN muted INTEGER NOT NULL DEFAULT 0')
        if 'scope' not in chat_columns:self.db.execute('ALTER TABLE chats ADD COLUMN scope TEXT')
        columns={row[1] for row in self.db.execute('PRAGMA table_info(messages)')}
        for name,kind in (('tx_hash','TEXT'),('heard_at','INTEGER'),('heard_hops','INTEGER')):
            if name not in columns:
                self.db.execute(f'ALTER TABLE messages ADD COLUMN {name} {kind}')
        self.db.execute('CREATE INDEX IF NOT EXISTS outgoing_hash ON messages(tx_hash)')
        # Pending messages are never silently retransmitted after a crash.
        self.db.execute("UPDATE messages SET status='interrupted' WHERE status='sending'")
        if self.get('channels_initialized') is None:
            self.db.execute("INSERT OR IGNORE INTO chats(id,name,kind,secret) VALUES('public','Public','channel',?)", (PUBLIC_KEY,))
            self.db.execute("INSERT INTO settings VALUES('channels_initialized','1')")
        self.db.commit()

    def get(self, key, default=None):
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set(self, key, value):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, str(value)))

    def join(self, name):
        name = "#" + name.strip().lstrip("#").lower()
        if not re.fullmatch(r"#[a-z0-9][a-z0-9_-]{0,29}", name):
            raise ValueError("Use 1–30 letters, numbers, _ or -")
        if self.db.execute("SELECT count(*) FROM chats WHERE kind='channel'").fetchone()[0] >= 32:
            if not self.db.execute("SELECT 1 FROM chats WHERE id=?", (name,)).fetchone():
                raise ValueError("Channel limit reached (32)")
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO chats(id,name,kind,secret) VALUES(?,?,'channel',?)", (name, name, hashlib.sha256(name.encode()).digest()[:16].hex()))
        return name

    def dm(self, key, name):
        with self.db:
            self.db.execute("INSERT INTO chats(id,name,kind) VALUES(?,?,'dm') ON CONFLICT(id) DO UPDATE SET name=excluded.name", (key, name))
        return key

    def join_public(self):
        if not self.db.execute("SELECT 1 FROM chats WHERE id='public'").fetchone():
            if self.db.execute("SELECT count(*) FROM chats WHERE kind='channel'").fetchone()[0]>=32:
                raise ValueError('Channel limit reached (32)')
            with self.db:
                self.db.execute("INSERT INTO chats(id,name,kind,secret) VALUES('public','Public','channel',?)",(PUBLIC_KEY,))
        return 'public'

    def leave(self,chat):
        row=self.db.execute('SELECT kind FROM chats WHERE id=?',(chat,)).fetchone()
        if not row or row['kind']!='channel':raise ValueError('Select a channel to leave')
        with self.db:
            self.db.execute('DELETE FROM messages WHERE chat=?',(chat,))
            self.db.execute('DELETE FROM chats WHERE id=?',(chat,))

    def is_muted(self,chat):
        row=self.db.execute('SELECT muted FROM chats WHERE id=?',(chat,)).fetchone()
        return bool(row and row[0])

    def mute(self,chat,value):
        with self.db:self.db.execute("UPDATE chats SET muted=? WHERE id=? AND kind='channel'",(int(bool(value)),chat))

    def set_scope(self,chat,value):
        value=value.strip().lower().lstrip('#')
        if value and not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,29}',value):raise ValueError('Use 1–30 letters, numbers, _ or -')
        with self.db:self.db.execute("UPDATE chats SET scope=? WHERE id=? AND kind='channel'",(value or None,chat))

    def clear_history(self,chat):
        with self.db:
            self.db.execute('DELETE FROM messages WHERE chat=?',(chat,))
            self.db.execute('UPDATE chats SET unread=0 WHERE id=?',(chat,))

    def chats(self):
        return [dict(r) for r in self.db.execute("""SELECT c.*,
          (SELECT text FROM messages WHERE chat=c.id ORDER BY id DESC LIMIT 1) preview,
          (SELECT timestamp FROM messages WHERE chat=c.id ORDER BY id DESC LIMIT 1) timestamp,
          (SELECT status FROM messages WHERE chat=c.id ORDER BY id DESC LIMIT 1) status
          FROM chats c ORDER BY COALESCE(timestamp,0) DESC,c.rowid""")]

    def history(self, chat, limit=100):
        rows = self.db.execute("SELECT * FROM messages WHERE chat=? ORDER BY id DESC LIMIT ?", (chat, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def add(self, chat, sender, text, timestamp=None, status='received', token=None, unread=False):
        with self.db:
            cur = self.db.execute("INSERT OR IGNORE INTO messages(chat,sender,text,timestamp,status,token) VALUES(?,?,?,?,?,?)", (chat, sender, text, timestamp or int(time.time()), status, token))
            if cur.rowcount and unread:
                self.db.execute("UPDATE chats SET unread=unread+1 WHERE id=?", (chat,))
            return cur.lastrowid if cur.rowcount else None

    def status(self, mid, status):
        with self.db:
            self.db.execute("UPDATE messages SET status=? WHERE id=?", (status, mid))
            if status in ('failed','interrupted'):
                self.db.execute('UPDATE messages SET tx_hash=NULL,heard_at=NULL,heard_hops=NULL WHERE id=?',(mid,))

    def bind_tx(self, mid, packet_hash):
        with self.db:
            self.db.execute("UPDATE messages SET tx_hash=?,status='sent' WHERE id=?",(packet_hash,mid))

    def heard(self, packet_hash, hops):
        if hops < 0:
            return False
        with self.db:
            cur=self.db.execute("""UPDATE messages SET heard_at=?,heard_hops=?
                WHERE tx_hash=? AND status IN ('sending','sent') AND heard_at IS NULL""",
                (int(time.time()),hops,packet_hash))
            return bool(cur.rowcount)

    def read(self, chat):
        with self.db:
            self.db.execute("UPDATE chats SET unread=0 WHERE id=? AND unread!=0", (chat,))
