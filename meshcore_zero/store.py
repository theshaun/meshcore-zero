"""Transactional local history. Only the radio worker and UI's event loop use this."""
import hashlib
import os
import re
import sqlite3
import time
from pathlib import Path

PUBLIC_KEY = "8b3387e9c5cdea6ac9e5edbaa115cd72"
PRESETS = {
    "US": dict(frequency=910525000, bandwidth=62500, spreading_factor=7, coding_rate=5, tx_power=20),
    "EU": dict(frequency=869618000, bandwidth=62500, spreading_factor=8, coding_rate=5, tx_power=14),
}


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
          CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, chat TEXT, sender TEXT, text TEXT, timestamp INTEGER, status TEXT, token TEXT UNIQUE);
          CREATE TABLE IF NOT EXISTS nodes(key TEXT PRIMARY KEY, data TEXT);
          CREATE INDEX IF NOT EXISTS history ON messages(chat,id);
        """)
        # Pending messages are never silently retransmitted after a crash.
        self.db.execute("UPDATE messages SET status='interrupted' WHERE status='sending'")
        self.db.execute("INSERT OR IGNORE INTO chats(id,name,kind,secret) VALUES('public','Public','channel',?)", (PUBLIC_KEY,))
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

    def read(self, chat):
        with self.db:
            self.db.execute("UPDATE chats SET unread=0 WHERE id=? AND unread!=0", (chat,))
