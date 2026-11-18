#!/usr/bin/env python3
"""Render synthetic store screenshots without opening a radio or real history."""
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from meshcore_zero.store import Store
from meshcore_zero.ui import UI


def main():
    with tempfile.TemporaryDirectory() as directory:
        store=Store(directory)
        store.set('name','Zero 💨')
        store.join('#testing')
        store.join('#local')
        store.dm('a'*64,'Ari 🪐')
        store.add('public','Sam','Hello from the mesh',timestamp=100)
        store.add('#local','Sam','Anyone heading outside?',timestamp=200)
        store.add('a'*64,'Ari 🪐','See you this afternoon!',timestamp=300)
        for sender,body,status in [('Zero 💨','Hello from my Cardputer!','sent'),
            ('Ari 🪐','Seen! The emoji looks great.','received'),
            ('Zero 💨','More room for the conversation now.','sent'),
            ('Ari 🪐','A longer message wraps onto the next line when it needs more space.','received')]:
            store.add('#testing',sender,body,timestamp=400,status=status)
        ui=UI(store)
        (ROOT/'screenshots').mkdir(exist_ok=True)
        ui.render().save(ROOT/'screenshots/inbox.png')
        ui.open_chat(next(c for c in store.chats() if c['id']=='#testing'))
        ui.render().save(ROOT/'screenshots/chat.png')
        store.db.close()


if __name__=='__main__': main()
