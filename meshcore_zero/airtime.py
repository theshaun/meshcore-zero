"""Private, identity-independent rolling-hour TX ledger.

Reservations are deliberately conservative: retain the entire packet until
one hour after its projected end, including uncertain hardware failures.
"""
from contextlib import closing
import math
import os
import sqlite3
import time


class AirtimeBudget:
    WINDOW = 3600
    LIMIT = 360

    def __init__(self, path, *, clock=time.time):
        self.path, self.clock = path, clock
        # Open per reservation: no connection survives radio teardown/restart.
        with closing(self._connect()) as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS tx (end REAL NOT NULL, seconds REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS clock (id INTEGER PRIMARY KEY, high REAL NOT NULL);
                INSERT OR IGNORE INTO clock VALUES (1, 0);
            ''')
        os.chmod(path, 0o600)

    def _connect(self):
        return sqlite3.connect(self.path, isolation_level=None)

    def reserve(self, seconds, *, limit=360):
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError('Invalid packet airtime')
        db = self._connect()
        try:
            # Multiple instances/processes cannot overspend the same ledger.
            db.execute('BEGIN IMMEDIATE')
            now = self.clock()
            high = db.execute('SELECT high FROM clock WHERE id=1').fetchone()[0]
            if not math.isfinite(now) or now < high:
                raise ValueError('Radio clock changed · check system time')
            db.execute('DELETE FROM tx WHERE end<=?', (now-self.WINDOW,))
            used = db.execute('SELECT COALESCE(SUM(seconds),0) FROM tx').fetchone()[0]
            if used + seconds > min(limit,self.LIMIT) + 1e-9:
                raise ValueError('Hourly airtime limit reached · receiving only')
            db.execute('INSERT INTO tx VALUES (?,?)', (now+seconds, seconds))
            db.execute('UPDATE clock SET high=? WHERE id=1', (now,))
            db.commit()
        finally:
            db.close()  # Uncommitted reservations automatically roll back.
