"""Small-screen UI, independent of hardware so every screen can be rendered in CI."""
import time
from PIL import Image, ImageDraw, ImageFont

BG = '#101d29'
PANEL = '#172938'
MUTED = '#8ba7b9'
TEXT = '#e8f3f9'
ACCENT = '#69dfca'
SELECT = '#254c65'


class UI:
    def __init__(self, store, backend=None):
        self.store, self.backend = store, backend
        self.menu = -1
        self.screen = 'inbox'
        self.selected = 0
        self.chat = None
        self.draft = ''
        self.drafts = {}
        self.scroll = 0
        self.toast = ''
        self.toast_until = 0
        self.running = True
        self.tasks = set()
        self.fonts = {}

    def notice(self, text):
        self.toast, self.toast_until = text, time.monotonic() + 4

    def font(self, size=12, bold=False):
        key = (size, bold)
        if key not in self.fonts:
            import os
            roots = ['/usr/share/fonts/truetype/dejavu', '/System/Library/Fonts/Supplemental']
            names = ['DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf', 'Arial Bold.ttf' if bold else 'Arial.ttf']
            for root, name in zip(roots, names):
                try:
                    self.fonts[key] = ImageFont.truetype(os.path.join(root, name), size)
                    break
                except OSError:
                    pass
            else:
                self.fonts[key] = ImageFont.load_default()
        return self.fonts[key]

    def open_chat(self, chat):
        self.chat = chat
        self.draft = self.drafts.get(chat['id'], '')
        self.store.read(chat['id'])
        self.screen, self.menu, self.scroll = 'chat', -1, 0

    def nodes(self):
        import json
        return [json.loads(r[0]) for r in self.store.db.execute('SELECT data FROM nodes ORDER BY key')]

    async def key(self, key):
        if key == 'tab':
            if self.screen == 'chat':
                self.drafts[self.chat['id']] = self.draft
            self.menu = (self.menu + 1) % 4
            self.screen = 'inbox'
            return
        if key == 'escape':
            if self.screen == 'chat':
                self.drafts[self.chat['id']] = self.draft
            if self.screen != 'inbox' or self.menu >= 0:
                self.screen, self.menu, self.selected, self.draft = 'inbox', -1, 0, ''
            else:
                self.running = False
            return
        if self.menu >= 0:
            if key in ('left', 'right'):
                self.menu = (self.menu + (1 if key == 'right' else -1)) % 4
            if key == 'enter':
                self.screen = ['inbox', 'join', 'nodes', 'settings'][self.menu]
                self.menu, self.selected, self.draft = -1, 0, ''
            return
        if self.screen in ('inbox', 'nodes', 'settings'):
            count = len(self.store.chats()) if self.screen == 'inbox' else len(self.nodes()) if self.screen == 'nodes' else 3
            if key in ('up', 'down'):
                self.selected = max(0, min(max(0, count - 1), self.selected + (1 if key == 'down' else -1)))
            elif key == 'enter':
                if self.screen == 'inbox' and count:
                    self.open_chat(self.store.chats()[min(self.selected,count-1)])
                elif self.screen == 'nodes' and count:
                    node = self.nodes()[self.selected]
                    if node.get('adv_type') != 1:
                        self.notice('Choose a chat node to send a DM')
                        return
                    cid = self.store.dm(node['public_key'], node['name'])
                    self.open_chat(next(c for c in self.store.chats() if c['id'] == cid))
                elif self.screen == 'settings':
                    if self.selected == 0:
                        self.store.set('region', 'EU' if self.store.get('region', 'US') == 'US' else 'US')
                        self.notice('Region saved · restart app to apply')
                    elif self.selected == 1:
                        self.screen, self.draft = 'name', self.store.get('name', 'MeshCore Zero')
                    elif self.backend and self.backend.engine:
                        try:
                            await self.backend.announce()
                        except Exception as exc:
                            self.notice(str(exc))
            return
        if self.screen == 'chat' and key in ('up','down'):
            self.scroll = max(0, self.scroll + (1 if key == 'up' else -1))
            return
        if key == 'backspace':
            self.draft = self.draft[:-1]
        elif key == 'enter':
            try:
                if self.screen == 'join':
                    cid = self.store.join(self.draft)
                    if self.backend:
                        self.backend.sync_channels()
                    self.open_chat(next(c for c in self.store.chats() if c['id'] == cid))
                elif self.screen == 'name':
                    if not self.draft.strip() or len(self.draft.encode()) > 24:
                        raise ValueError('Name must be 1–24 bytes')
                    self.store.set('name', self.draft.strip())
                    if self.backend and self.backend.engine:
                        self.backend.engine.set_advert_name(self.draft.strip())
                    self.screen, self.draft = 'settings', ''
                elif self.screen == 'chat':
                    if not self.backend:
                        raise ValueError('Preview mode · no radio')
                    # Validate before clearing, then let TX run without blocking input/RX.
                    if not self.draft.strip():
                        return
                    await self.send()
            except (ValueError, RuntimeError) as exc:
                self.notice(str(exc))
        elif len(key) == 1 and key.isprintable():
            limit = 150 if self.screen == 'chat' else 31
            if len((self.draft + key).encode()) <= limit:
                self.draft += key

    async def send(self):
        import asyncio
        text, chat = self.draft, dict(self.chat)
        if not self.backend.engine:
            raise ValueError('Radio offline · message not sent')
        overhead = len((self.backend.engine.prefs.node_name + ': ').encode()) if chat['kind'] == 'channel' else 0
        if len(text.encode()) + overhead > 150:
            raise ValueError(f'Max {150-overhead} bytes for this conversation')
        async def work():
            try:
                await self.backend.send(chat, text)
            except Exception as exc:
                self.drafts[chat['id']] = text
                if self.chat and self.chat['id'] == chat['id'] and not self.draft:
                    self.draft = text
                self.notice(str(exc))
        task = asyncio.create_task(work())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        self.draft = ''
        self.drafts[chat['id']] = ''
        self.scroll = 0

    def render(self):
        img = Image.new('RGB', (320, 170), BG)
        d = ImageDraw.Draw(img)
        def text(x, y, value, color=TEXT, size=12, bold=False, width=304):
            value = str(value).replace('\n', ' ')
            font = self.font(size, bold)
            while value and d.textlength(value, font=font) > width:
                value = value[:-2] + '…' if not value.endswith('…') else value[:-2] + '…'
            d.text((x, y), value, font=font, fill=color)
        text(9, 2, 'MeshCore', size=12, bold=True)
        region = self.backend.region if self.backend and self.backend.engine else self.store.get('region','US')
        text(92, 3, region, ACCENT, 10)
        ready = self.backend and self.backend.engine
        d.ellipse((270,6,275,11), fill=ACCENT if ready else '#e7b86e')
        text(281, 2, time.strftime('%H:%M'), MUTED, 10)
        d.rectangle((0,20,319,40), fill=PANEL)
        for i, (x, title) in enumerate([(8,'Chats'),(64,'Join Channel'),(169,'Nodes'),(236,'Settings')]):
            if i == self.menu:
                d.rounded_rectangle((x-4,22,x + [45,96,57,72][i],39),3, fill=SELECT)
            text(x,23,title,ACCENT if i==self.menu else MUTED,10,bold=i==self.menu)
        hint = 'Tab menu    ↑↓ select    Enter open'
        if self.screen == 'inbox':
            chats = self.store.chats()
            self.selected = min(self.selected, max(0,len(chats)-1))
            start = max(0,self.selected-2)
            for i, chat in enumerate(chats[start:start+3],start):
                y = 43 + (i-start)*35
                selected = i == self.selected and self.menu < 0
                d.rounded_rectangle((5,y,314,y+33),4,fill=SELECT if selected else PANEL)
                if selected:
                    d.rounded_rectangle((5,y+4,7,y+29),1, fill=ACCENT)
                text(13,y+1,'#' if chat['kind']=='channel' else '@',ACCENT,14,True)
                text(29,y+1,chat['name'],size=12,bold=True,width=228)
                if chat['unread']:
                    text(284,y+1,str(chat['unread']),ACCENT,10,width=25)
                preview = chat['preview'] or ('Say hello to the mesh' if chat['id']=='public' else 'No messages yet')
                if chat['status'] in ('failed','unconfirmed','sending','interrupted'):
                    preview = chat['status'].capitalize() + ' · ' + preview
                text(29,y+17,preview,MUTED,10,width=273)
        elif self.screen in ('join','name'):
            text(10,47,'Join a hashtag channel' if self.screen=='join' else 'Your node name',size=14,bold=True)
            text(10,69,'Same hashtag connects everyone.' if self.screen=='join' else 'Shown to other people on the mesh.',MUTED,10)
            d.rounded_rectangle((8,94,311,119),4,fill=SELECT)
            text(15,98,(self.draft or ('#asheville' if self.screen=='join' else 'Your name'))+'|',ACCENT,13,width=287)
            text(10,129,'Hashtag channels are public.' if self.screen=='join' else 'Enter saves your name.',MUTED,10)
            hint = 'Enter save    Esc back'
        elif self.screen == 'nodes':
            nodes = self.nodes()
            if not nodes:
                text(12,58,'Listening for nodes',size=15,bold=True)
                text(12,84,'Nearby adverts will appear here.',MUTED,11)
                text(12,105,'Settings → Announce to introduce yourself.',MUTED,10)
            for i,node in enumerate(nodes[max(0,self.selected-2):self.selected+3]):
                absolute = max(0,self.selected-2)+i
                if i >= 3: break
                y=44+i*35
                d.rounded_rectangle((5,y,314,y+33),4,fill=SELECT if absolute==self.selected else PANEL)
                text(12,y+1,node.get('name','Unknown'),bold=True,width=290)
                text(12,y+18,('Chat' if node.get('adv_type')==1 else 'Infrastructure')+' · '+node['public_key'][:12],MUTED,10)
            hint = '↑↓ select    Enter DM    Esc back'
        elif self.screen == 'settings':
            for i,label in enumerate(['Region: '+self.store.get('region','US')+'  (restart to apply)', 'Name: '+self.store.get('name','MeshCore Zero'), 'Announce this node']):
                y=44+i*30
                d.rounded_rectangle((5,y,314,y+28),4, fill=SELECT if i==self.selected else PANEL)
                text(12,y+6,label,size=11,width=290)
            status = (self.backend.error or self.backend.state) if self.backend else 'Preview · no radio'
            text(10,137,status,MUTED,9,width=300)
            hint='↑↓ select    Enter change    Esc back'
        elif self.screen == 'chat':
            text(9,43,self.chat['name'],ACCENT,11,True,width=300)
            history = self.store.history(self.chat['id'])
            lines=[]
            for msg in history:
                prefix = msg['sender'] + (' · '+msg['status'] if msg['sender']=='You' else '')
                lines.append((prefix,ACCENT if msg['sender']=='You' else MUTED))
                words = msg['text'].split(' ')
                line=''
                for word in words:
                    for char in word+' ':
                        if d.textlength(line+char,font=self.font(11)) > 296:
                            lines.append((line,TEXT)); line=''
                        line+=char
                if line: lines.append((line,TEXT))
            self.scroll=min(self.scroll,max(0,len(lines)-5))
            end=max(0,len(lines)-self.scroll)
            visible=lines[max(0,end-5):end]
            for i,(line,color) in enumerate(visible):
                text(10,60+i*13,line,color,11,width=300)
            if not history: text(10,78,'Start the conversation.',MUTED,12)
            d.rounded_rectangle((5,130,314,151),4,fill=SELECT)
            # Show the tail while typing, avoiding a hidden caret on long drafts.
            tail=self.draft
            while d.textlength(tail,font=self.font(11)) > 287: tail=tail[1:]
            text(11,133,(tail+'|') if self.draft else 'Type a message…',TEXT if self.draft else MUTED,11)
            hint='Enter send    ↑↓ history    Esc back'
            self.store.read(self.chat['id'])
        d.rectangle((0,154,319,169),fill=BG)
        text(8,157,hint,MUTED,9)
        if self.toast and time.monotonic() < self.toast_until:
            d.rounded_rectangle((5,129,314,152),4,fill='#38515b')
            text(11,134,self.toast,TEXT,10,width=296)
        return img
