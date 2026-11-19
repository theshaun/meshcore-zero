"""Small-screen UI, independent of hardware so every screen can be rendered in CI."""
import time
from PIL import Image, ImageDraw, ImageFont
from .store import radio_config
from .regions import PRESETS, NAMES
from .text import Text

BG = '#101d29'
PANEL = '#172938'
MUTED = '#8ba7b9'
TEXT = '#e8f3f9'
ACCENT = '#69dfca'
SELECT = '#254c65'
GREEN = '#4de27a'
UNCONFIRMED = '#52616d'


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
        self.text = Text(self.font)
        self._chat_cache_key = None
        self._chat_cache = None
        from .update import Updater
        self.updater = Updater()
        self.update_state = 'idle'
        self.update_message = ''
        self.password = ''
        self.restart_requested = False
        self.battery = None
        import asyncio
        self.launch_state = ''
        self.launch_error = ''
        self.launch_ack = asyncio.Event()

    def notice(self, text):
        self.toast, self.toast_until = text, time.monotonic() + 4

    def render_key(self, include_draft=True):
        """Visible model revision; idle input polling must not repaint the UI."""
        return (self.store.db.total_changes, self.screen, self.menu, self.selected,
            self.chat['id'] if self.chat else None, self.draft if include_draft else None, self.scroll,
            self.toast if time.monotonic() < self.toast_until else '',
            self.update_state, self.update_message, len(self.password), self.battery,
            self.launch_state, self.launch_error,
            self.backend.state if self.backend else '',
            self.backend.error if self.backend else '')

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

    def local_name(self):
        if self.backend and self.backend.engine:
            return self.backend.engine.prefs.node_name
        return self.store.get('name','MeshCore Zero')

    def chat_lines(self, history):
        lines = []
        for msg in history:
            outgoing = msg['status'] != 'received'
            # Old releases persisted "You". Keep that history readable while
            # new messages retain the node name used at transmission time.
            name = self.local_name() if outgoing and msg['sender'] == 'You' else msg['sender']
            body = msg['text']
            if msg['status'] in ('failed','unconfirmed','interrupted'):
                body += ' ['+msg['status']+']'
            spans=[(name+': ',ACCENT if outgoing else MUTED),(body,TEXT)]
            if outgoing:
                color=GREEN if msg.get('heard_at') or msg['status']=='delivered' else UNCONFIRMED
                spans.insert(0,('● ',color))
            lines.extend(self.text.wrap(spans,300,11))
        return lines

    async def update_work(self, action):
        import asyncio
        self.update_state = 'busy'
        self.update_message = {'check':'Checking GitHub…','download':'Downloading and verifying…','install':'Installing. Keep power connected.'}[action]
        try:
            if action == 'check':
                available = await asyncio.to_thread(self.updater.check)
                self.update_state = 'available' if available else 'current'
                self.update_message = ('Available: '+self.updater.release[0]) if available else 'You have the latest version.'
            elif action == 'download':
                await asyncio.to_thread(self.updater.download)
                self.update_state = 'password'
                self.update_message = 'Device sudo password (blank if none):'
            else:
                password, self.password = self.password, ''
                await self.updater.install(password)
                password = ''
                self.restart_requested = True
                self.running = False
        except Exception:
            self.password = ''
            self.update_state = 'error'
            self.update_message = 'Update failed. Check network / password.'

    def start_update(self, action):
        import asyncio
        self.update_state = 'busy'
        task=asyncio.create_task(self.update_work(action))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def key(self, key):
        if self.launch_state:
            if key=='enter':
                if self.launch_state=='conflict': self.launch_ack.set()
                elif self.launch_state=='error': self.running=False
            return
        if self.screen == 'update':
            if self.update_state == 'busy': return
            if key in ('escape','tab'):
                self.password = ''
                self.updater.cleanup()
                self.screen, self.selected = 'settings', 4
            elif key == 'enter':
                self.start_update('download' if self.update_state=='available' else 'install' if self.update_state=='password' else 'check')
            elif self.update_state == 'password':
                if key == 'backspace': self.password=self.password[:-1]
                elif len(key)==1 and key.isprintable() and len(self.password)<128: self.password+=key
            return
        if self.screen == 'regions':
            regions=list(PRESETS)
            if key in ('up','down'):
                self.selected=max(0,min(len(regions)-1,self.selected+(1 if key=='down' else -1)))
            elif key in ('escape','enter'):
                if key=='enter':
                    chosen=regions[self.selected]
                    self.store.set('region',chosen)
                    self.notice('JP experimental · see README' if chosen=='JP' else 'Region saved · restart app to apply')
                self.screen,self.selected='settings',0
            elif key=='tab':
                self.screen,self.menu,self.selected='inbox',0,0
            return
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
                self.menu, self.selected, self.draft = -1, 0, '#' if self.screen == 'join' else ''
            return
        if self.screen in ('inbox', 'nodes', 'settings'):
            count = len(self.store.chats()) if self.screen == 'inbox' else len(self.nodes()) if self.screen == 'nodes' else 5
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
                        self.screen='regions'
                        self.selected=list(PRESETS).index(self.store.get('region','US'))
                    elif self.selected == 1:
                        region = self.store.get('region', 'US')
                        coding_rate = radio_config(self.store, region)['coding_rate']
                        self.store.set('coding_rate_' + region, 5 if coding_rate == 8 else coding_rate + 1)
                        self.notice('Coding rate saved · restart to apply')
                    elif self.selected == 2:
                        self.screen, self.draft = 'name', self.store.get('name', 'MeshCore Zero')
                    elif self.selected == 4:
                        self.screen = 'update'
                        self.start_update('check')
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
            self.draft = self.draft[:-1] if self.screen != 'join' or len(self.draft) > 1 else '#'
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
            if self.screen == 'join' and key == '#' and self.draft == '#':
                return
            limit = 150 if self.screen == 'chat' else 31
            if len((self.draft + key).encode()) <= limit:
                self.draft += key

    async def send(self):
        import asyncio
        text, chat = self.draft, dict(self.chat)
        if not self.backend.engine:
            raise ValueError('Radio offline · message not sent')
        overhead = len((self.backend.engine.prefs.node_name + ': ').encode()) if chat['kind'] == 'channel' else 0
        limit=16 if getattr(self.backend,'region','US')=='JP' else 150
        if len(text.encode()) + overhead > limit:
            raise ValueError(f'Max {max(0,limit-overhead)} bytes for this conversation')
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
        if self.launch_state:
            return self.draw_launch_notice()
        if self.screen == 'chat' and self._chat_cache_key == self.render_key(False):
            img=self._chat_cache.copy()
            self.draw_composer(img)
            self.draw_notice(img)
            return img
        img = Image.new('RGB', (320, 170), BG)
        d = ImageDraw.Draw(img)
        def text(x, y, value, color=TEXT, size=12, bold=False, width=304):
            return self.text.draw(img,(x,y),value,color,size,bold,width)
        self.draw_tabs(img)
        hint = 'Tab menu    ↑↓ select    Enter open'
        if self.screen == 'inbox':
            chats = self.store.chats()
            self.selected = min(self.selected, max(0,len(chats)-1))
            start = max(0,self.selected-3)
            for i, chat in enumerate(chats[start:start+4],start):
                y = 23 + (i-start)*32
                selected = i == self.selected and self.menu < 0
                d.rounded_rectangle((5,y,314,y+30),4,fill=SELECT if selected else PANEL)
                if selected:
                    d.rounded_rectangle((5,y+4,7,y+26),1, fill=ACCENT)
                if chat['kind']=='dm':
                    text(13,y+1,'@',ACCENT,14,True)
                left = 29 if chat['kind']=='dm' else 13
                text(left,y+1,chat['name'],size=12,bold=True,width=270-left)
                if chat['unread']:
                    text(284,y+1,str(chat['unread']),ACCENT,10,width=25)
                preview = chat['preview'] or ('Say hello to the mesh' if chat['id']=='public' else 'No messages yet')
                if chat['status'] in ('failed','unconfirmed','sending','interrupted'):
                    preview = chat['status'].capitalize() + ' · ' + preview
                text(left,y+17,preview,MUTED,10,width=302-left)
        elif self.screen in ('join','name'):
            text(10,27,'Join a hashtag channel' if self.screen=='join' else 'Your node name',size=14,bold=True)
            text(10,49,'Same hashtag connects everyone.' if self.screen=='join' else 'Shown to other people on the mesh.',MUTED,10)
            d.rounded_rectangle((8,74,311,99),4,fill=SELECT)
            text(15,78,(self.draft or ('#asheville' if self.screen=='join' else 'Your name'))+'|',ACCENT,13,width=287)
            text(10,109,'Hashtag channels are public.' if self.screen=='join' else 'Enter saves your name.',MUTED,10)
            hint = 'Enter save    Esc back'
        elif self.screen == 'nodes':
            nodes = self.nodes()
            if not nodes:
                text(12,38,'Listening for nodes',size=15,bold=True)
                text(12,64,'Nearby adverts will appear here.',MUTED,11)
                text(12,85,'Settings → Announce to introduce yourself.',MUTED,10)
            for i,node in enumerate(nodes[max(0,self.selected-3):self.selected+4]):
                absolute = max(0,self.selected-3)+i
                if i >= 4: break
                y=23+i*32
                d.rounded_rectangle((5,y,314,y+30),4,fill=SELECT if absolute==self.selected else PANEL)
                text(12,y+1,node.get('name','Unknown'),bold=True,width=290)
                text(12,y+18,('Chat' if node.get('adv_type')==1 else 'Infrastructure')+' · '+node['public_key'][:12],MUTED,10)
            hint = '↑↓ select    Enter DM    Esc back'
        elif self.screen == 'regions':
            regions=list(PRESETS)
            start=max(0,self.selected-3)
            for i,region in enumerate(regions[start:start+4],start):
                cfg=radio_config(self.store,region)
                y=23+(i-start)*32
                d.rounded_rectangle((5,y,314,y+30),4,fill=SELECT if i==self.selected else PANEL)
                label=NAMES[region]+(' · experimental' if region=='JP' else '')
                text(12,y+1,label,bold=True,width=292)
                detail=f"{cfg['frequency']/1e6:.3f} MHz  SF{cfg['spreading_factor']}  BW{cfg['bandwidth']/1000:g}  CR4/{cfg['coding_rate']}"
                text(12,y+18,detail,MUTED,9,width=292)
            hint='↑↓ select   Enter save   Restart to apply'
        elif self.screen == 'settings':
            cr = radio_config(self.store)['coding_rate']
            for i,label in enumerate(['Region: '+self.store.get('region','US')+'  (restart to apply)', f'Coding rate: 4/{cr}  (restart to apply)', 'Name: '+self.store.get('name','MeshCore Zero'), 'Announce this node', 'Update app']):
                y=23+i*22
                d.rounded_rectangle((5,y,314,y+20),4, fill=SELECT if i==self.selected else PANEL)
                text(12,y+3,label,size=11,width=290)
            status = (self.backend.error or self.backend.state) if self.backend else 'Preview · no radio'
            text(10,139,status,MUTED,9,width=300)
            hint='↑↓ select    Enter change    Esc back'
        elif self.screen == 'update':
            from . import __version__
            text(10,29,'App update',size=14,bold=True)
            text(10,54,'Installed: '+__version__,MUTED,11)
            text(10,76,self.update_message,size=11,width=300)
            if self.update_state == 'password':
                d.rounded_rectangle((8,99,311,123),4,fill=SELECT)
                text(14,103,'*'*min(35,len(self.password))+'|',ACCENT,12,width=290)
            hint = ('Enter download   Esc back' if self.update_state=='available' else
                    'Enter install   Esc back' if self.update_state=='password' else
                    'Please wait…' if self.update_state=='busy' else 'Enter check again   Esc back')
        elif self.screen == 'chat':
            text(9,23,self.chat['name'],ACCENT,11,True,width=300)
            history = self.store.history(self.chat['id'])
            lines=self.chat_lines(history)
            self.scroll=min(self.scroll,max(0,len(lines)-7))
            end=max(0,len(lines)-self.scroll)
            visible=lines[max(0,end-7):end]
            for i,line in enumerate(visible):
                x=10
                for value,color in line:
                    if value=='● ' and color in (GREEN,UNCONFIRMED):
                        d.ellipse((x+1,42+i*13,x+4,45+i*13),fill=color)
                        x+=self.text.width(value,11)
                    else:
                        x=text(x,37+i*13,value,color,11,width=310-x)
            if not history: text(10,58,'Start the conversation.',MUTED,12)
            self.draw_composer(img)
            hint='Enter send    ↑↓ history    Esc back'
            self.store.read(self.chat['id'])
        d.rectangle((0,154,319,169),fill=BG)
        text(8,157,hint,MUTED,9)
        self.draw_notice(img)
        if self.screen == 'chat':
            self._chat_cache_key=self.render_key(False)
            self._chat_cache=img.copy()
        return img

    def draw_launch_notice(self):
        img=Image.new('RGB',(320,170),BG)
        d=ImageDraw.Draw(img)
        self.text.draw(img,(12,9),'MeshCore',ACCENT,14,True,width=296)
        if self.launch_state=='conflict':
            lines=['MeshZero is running in the background.',
                   'It will be closed so MeshCore can',
                   'use the LoRa CAP.']
        elif self.launch_state=='stopping':
            lines=['Closing MeshZero…','Waiting for the radio to be released.']
        elif self.launch_state=='error':
            lines=[self.launch_error,'The radio has not been started.',
                   'Check MeshZero, then reopen this app.']
        else:
            lines=['Checking the radio service…']
        for i,line in enumerate(lines):
            self.text.draw(img,(12,43+i*19),line,TEXT,11,width=296)
        if self.launch_state in ('conflict','error'):
            d.rounded_rectangle((108,124,211,151),4,fill=SELECT,outline=ACCENT)
            width=self.text.width('Okay',12,True)
            self.text.draw(img,((320-width)/2,129),'Okay',ACCENT,12,True,width=96)
        return img

    def active_tab(self):
        if self.screen in ('inbox','chat'): return 0
        if self.screen == 'join': return 1
        if self.screen == 'nodes': return 2
        return 3

    def draw_tabs(self,img):
        d=ImageDraw.Draw(img)
        d.rectangle((0,0,319,20),fill=PANEL)
        active=self.active_tab()
        for i,title in enumerate(('Chats','Join','Nodes','Settings')):
            left=i*72
            selected=i==active
            bounds=(left+3,2,left+68,18)
            if selected: d.rounded_rectangle(bounds,3,fill=SELECT)
            if i==self.menu: d.rounded_rectangle(bounds,3,outline=ACCENT)
            width=self.text.width(title,10,selected)
            self.text.draw(img,(left+(72-width)/2,3),title,
                ACCENT if selected else MUTED,10,selected,width=66)
        # Fuel-gauge capacity only: never infer a charge level from voltage.
        d.rounded_rectangle((296,5,315,15),2,outline=MUTED)
        d.rectangle((316,8,317,12),fill=MUTED)
        if self.battery is None:
            d.line((303,10,308,10),fill=MUTED)
        else:
            fill=round(16*max(0,min(100,self.battery))/100)
            if fill: d.rectangle((298,7,297+fill,13),fill=TEXT)

    def draw_composer(self,img):
        from .text import units
        d=ImageDraw.Draw(img)
        d.rectangle((5,129,314,152),fill=BG)
        d.rounded_rectangle((5,130,314,151),4,fill=SELECT)
        tail=list(units(self.draft))
        while tail and self.text.width(''.join(p for p,_ in tail),11) > 287:
            tail.pop(0)
        tail=''.join(p for p,_ in tail)
        self.text.draw(img,(11,133),(tail+'|') if self.draft else 'Type a message…',
            TEXT if self.draft else MUTED,11,width=297)

    def draw_notice(self,img):
        if self.toast and time.monotonic() < self.toast_until:
            bounds=(5,154,314,169) if self.screen=='chat' else (5,129,314,152)
            ImageDraw.Draw(img).rounded_rectangle(bounds,4,fill='#38515b')
            self.text.draw(img,(11,bounds[1]+2),self.toast,TEXT,10,width=296)
