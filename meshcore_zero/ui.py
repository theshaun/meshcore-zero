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
TAB_SCREENS = ('inbox','join','nodes','map','settings')
TAB_TITLES = ('Chats','Join','Nodes','Map','Settings')

UNCONFIRMED = '#52616d'


def draw_globe(draw,x,y,size,color):
    draw.ellipse((x,y,x+size,y+size),outline=color)
    draw.ellipse((x+size//3,y,x+size-size//3,y+size),outline=color)
    draw.line((x,y+size//2,x+size,y+size//2),fill=color)


class UI:
    def __init__(self, store, backend=None):
        self.store, self.backend = store, backend
        self.menu = -1
        self.region_catalog=None
        self.presets_busy=False
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
        from pathlib import Path
        data_root=Path(store.db.execute('PRAGMA database_list').fetchone()[2]).parent
        self.updater = Updater(log_path=data_root/'update.log',cache_dir=data_root/'update-cache')
        self.update_state = 'idle'
        self.update_message = ''
        self.update_stage = ''
        self.update_done = self.update_total = None
        self.update_started = self.update_stage_started = 0
        self.password = ''
        self.restart_requested = False
        self.startup_release = None
        self.startup_update_choice = 0
        self.join_draft = '#'
        from .join_ui import JoinUI
        self.join_ui = JoinUI(self)
        self.leave_target = None
        self.leave_choice = 1
        from .identity_ui import IdentityUI
        self.identity_ui = IdentityUI(self)
        from .channel_ui import ChannelUI
        self.channel_ui = ChannelUI(self)
        from .protocol_ui import ProtocolUI
        self.protocol_ui = ProtocolUI(self)
        from .gps import GPS
        self.gps = GPS(self)
        from .map_ui import MapUI
        self.map_ui = MapUI(self)
        self.pending_restore = None
        from .backup_ui import BackupUI
        self.backup_ui = BackupUI(self)
        result=store.get('restore_result')
        if result:
            self.backup_ui.result=result;self.backup_ui.state='result';self.screen='backup'
            with store.db:store.db.execute("DELETE FROM settings WHERE key='restore_result'")
        self.repeater = None
        self.repeater_state = ''
        self.repeater_password = ''
        self.repeater_choice = 0
        self.repeater_stats = {}
        self.repeater_clock = None
        self.repeater_error = ''
        self.repeater_task = None
        from .repeater_passwords import RepeaterPasswords
        self.repeater_passwords = RepeaterPasswords(store)
        self.battery = None
        import asyncio
        self.launch_state = ''
        self.launch_error = ''
        self.launch_ack = asyncio.Event()

    def notice(self, text):
        self.toast, self.toast_until = text, time.monotonic() + 4

    def switch_tab(self, index):
        if self.screen == 'chat':
            self.drafts[self.chat['id']] = self.draft
        if self.screen == 'join':
            self.join_ui.clear_secret()
            self.join_draft = self.draft
        self.screen = TAB_SCREENS[index]
        self.menu, self.selected = -1, 0
        self.draft = self.join_draft if index == 1 else ''
        if index==1:self.join_ui.type=0;self.join_ui.field=0

    async def repeater_work(self, public_key, password, save_password=None):
        from .repeater import request_status
        try:
            self.repeater_stats,self.repeater_clock=await request_status(self.backend,public_key,password)
            self.repeater_state='result'
            try:
                if save_password is True:self.repeater_passwords.save(public_key,password)
                elif save_password is False:self.repeater_passwords.forget(public_key)
            except Exception:
                self.notice('Status received · password could not be saved')
        except Exception as exc:
            self.repeater_error=str(exc)
            self.repeater_state='error'
        finally:
            password=''

    def start_repeater_status(self, save_password=None):
        import asyncio
        password,self.repeater_password=self.repeater_password,''
        self.repeater_state='busy'
        task=asyncio.create_task(self.repeater_work(self.repeater['public_key'],password,save_password))
        self.repeater_task=task
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def render_key(self, include_draft=True):
        """Visible model revision; idle input polling must not repaint the UI."""
        return (self.store.db.total_changes, self.screen, self.menu, self.selected,
            self.chat['id'] if self.chat else None, self.draft if include_draft else None, self.scroll,
            self.toast if time.monotonic() < self.toast_until else '',
            self.update_state, self.update_message, len(self.password), self.battery,
            self.update_stage,self.update_done,self.update_total,
            int(time.monotonic()-self.update_started) if self.update_state=='busy' and self.update_started else None,
            self.launch_state, self.launch_error,
            tuple(self.startup_release) if self.startup_release else None, self.startup_update_choice,
            self.repeater_state, self.repeater_choice, len(self.repeater_password),
            repr(self.repeater_stats), self.repeater_clock, self.repeater_error,
            self.leave_target['id'] if self.leave_target else None,self.leave_choice,self.identity_ui.render_key(),self.channel_ui.render_key(),self.protocol_ui.render_key(),self.backup_ui.render_key(),self.map_ui.render_key(),self.join_ui.render_key(),
            self.backend.state if self.backend else '',
            self.backend.error if self.backend else '')

    def region_choices(self):
        if self.region_catalog is None:
            from .preset_catalog import catalog
            self.region_catalog=catalog(self.store)
        return self.region_catalog

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

    def update_progress(self,stage,done=None,total=None):
        labels={'check':'Checking GitHub…','manifest':'Fetching checksum…',
            'connect':'Connecting to download…','download':'Downloading package…',
            'verify_download':'Verifying download…','authenticate':'Authenticating…',
            'stage_package':'Staging package…','verify_package':'Verifying package…',
            'metadata':'Checking package details…','prepare_install':'Preparing installation…',
            'dependencies':'Downloading dependencies…','installing':'Installing package…',
            'finish':'Finishing installation…'}
        if stage!=self.update_stage:self.update_stage_started=time.monotonic()
        self.update_stage=stage
        self.update_message=labels.get(stage,'Updating…')
        self.update_done,self.update_total=done,total

    async def update_work(self, action):
        import asyncio
        self.update_state = 'busy'
        self.update_started=time.monotonic()
        self.update_stage='';self.update_done=self.update_total=None
        loop=asyncio.get_running_loop()
        def progress(*args):loop.call_soon_threadsafe(self.update_progress,*args)
        self.update_message = {'check':'Checking GitHub…','download':'Downloading and verifying…','install':'Installing. Keep power connected.'}[action]
        try:
            if action == 'check':
                available = await asyncio.to_thread(self.updater.check,progress=progress)
                self.update_state = 'available' if available else 'current'
                self.update_message = ('Available: '+self.updater.release[0]) if available else 'You have the latest version.'
            elif action == 'download':
                await asyncio.to_thread(self.updater.download,progress)
                self.update_state = 'password'
                self.update_message = 'Device sudo password (blank if none):'
            else:
                password, self.password = self.password, ''
                await self.updater.install(password,progress)
                password = ''
                self.restart_requested = True
                self.running = False
        except Exception:
            self.password = ''
            self.update_state = 'error'
            self.update_message = 'Update failed. Check network / password.'
            self.update_stage='';self.update_done=self.update_total=None

    def start_update(self, action):
        import asyncio
        self.update_state = 'busy'
        task=asyncio.create_task(self.update_work(action))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def key(self, key):
        if self.launch_state:
            if self.launch_state=='conflict' and key=='escape':
                self.running=False
                self.launch_ack.set()
            if key=='enter':
                if self.launch_state=='conflict': self.launch_ack.set()
                elif self.launch_state=='error': self.running=False
            return
        if self.startup_release:
            if key in ('tab','left','right','up','down'):
                self.startup_update_choice = 1-self.startup_update_choice
            elif key == 'escape' or key == 'enter' and self.startup_update_choice == 1:
                self.startup_release = None
            elif key == 'enter':
                self.updater.release = tuple(self.startup_release)
                self.startup_release = None
                if self.screen == 'chat':
                    self.drafts[self.chat['id']] = self.draft
                self.screen = 'update'
                self.start_update('download')
            return
        if self.screen=='join':
            await self.join_ui.key(key)
            return
        if self.screen in ('map','map_position','map_details','gps_sharing'):
            await self.map_ui.key(key)
            return
        if self.screen=='backup':
            await self.backup_ui.key(key)
            return
        if self.screen=='protocol':
            await self.protocol_ui.key(key)
            return
        if self.screen=='channel_options':
            await self.channel_ui.key(key)
            return
        if self.screen=='identity':
            await self.identity_ui.key(key)
            return
        if self.leave_target:
            if key in ('tab','up','down','left','right'):self.leave_choice=1-self.leave_choice
            elif key=='escape' or key=='enter' and self.leave_choice==1:self.leave_target=None
            elif key=='enter':
                cid=self.leave_target['id']
                try:
                    if self.backend:self.backend.leave_channel(cid)
                    else:self.store.leave(cid)
                    self.drafts.pop(cid,None)
                    if self.chat and self.chat['id']==cid:self.chat=None;self.draft=''
                    self.leave_target=None
                    self.selected=min(self.selected,max(0,len(self.store.chats())-1))
                    self.notice('Channel left')
                except ValueError as exc:self.notice(str(exc))
            return
        if self.screen == 'repeater':
            if key == 'escape':
                if self.repeater_task and not self.repeater_task.done():self.repeater_task.cancel()
                self.repeater_password=''
                self.screen='nodes'
            elif key=='backspace' and self.repeater_state in ('confirm','result','error'):
                self.repeater_passwords.forget(self.repeater['public_key'])
                self.notice('Saved password removed')
            elif self.repeater_state in ('confirm','save'):
                if key in ('tab','left','right','up','down'):self.repeater_choice=1-self.repeater_choice
                elif key=='enter':
                    if self.repeater_state=='save':
                        self.start_repeater_status(save_password=self.repeater_choice==0)
                    elif self.repeater_choice==0:
                        saved=self.repeater_passwords.get(self.repeater['public_key'])
                        if saved is not None:
                            self.repeater_password=saved
                            self.start_repeater_status()
                        else:self.repeater_state='password'
                    else:self.screen='nodes'
            elif self.repeater_state=='password':
                if key=='backspace':self.repeater_password=self.repeater_password[:-1]
                elif key=='enter':self.repeater_state='save';self.repeater_choice=1
                elif len(key)==1 and key.isprintable():
                    if len((self.repeater_password+key).encode())<=15:self.repeater_password+=key
                    else:self.notice('Password limit: 15 UTF-8 bytes')
            elif self.repeater_state in ('result','error') and key=='enter':
                saved=self.repeater_passwords.get(self.repeater['public_key']) if self.repeater_state=='result' else None
                if saved is not None:
                    self.repeater_password=saved;self.start_repeater_status()
                else:self.repeater_state='password';self.repeater_password=''
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
            regions=list(self.region_choices())
            if key in ('up','down'):
                self.selected=max(0,min(len(regions)-1,self.selected+(1 if key=='down' else -1)))
            elif key in ('escape','enter'):
                if key=='enter':
                    chosen=regions[self.selected]
                    from .preset_catalog import select_profile
                    try:select_profile(self.store,self.region_choices()[chosen])
                    except ValueError as exc:self.notice(str(exc));return
                    self.notice('JP experimental · see README' if chosen=='JP' else 'Region saved · restart app to apply')
                self.screen,self.selected='settings',0
                self.region_catalog=None
            elif key=='tab':
                self.region_catalog=None;self.switch_tab(0)
            elif key=='r':
                import asyncio
                from .preset_catalog import refresh
                task=asyncio.create_task(refresh(self,manual=True));self.tasks.add(task);task.add_done_callback(self.tasks.discard)
            return
        if key == 'tab':
            self.switch_tab((self.active_tab()+1)%len(TAB_SCREENS))
            return
        if key == 'escape':
            if self.screen == 'chat':
                self.drafts[self.chat['id']] = self.draft
            if self.screen != 'inbox' or self.menu >= 0:
                self.screen, self.menu, self.selected, self.draft = 'inbox', -1, 0, ''
            else:
                self.running = False
            return
        if self.screen in ('inbox', 'nodes', 'settings'):
            count = len(self.store.chats()) if self.screen == 'inbox' else len(self.nodes()) if self.screen == 'nodes' else 10
            if key=='backspace' and self.screen=='inbox' and count:
                chat=self.store.chats()[min(self.selected,count-1)]
                if chat['kind']=='channel':self.channel_ui.open(chat)
                return
            if key in ('up', 'down'):
                self.selected = max(0, min(max(0, count - 1), self.selected + (1 if key == 'down' else -1)))
            elif key == 'enter':
                if self.screen == 'inbox' and count:
                    self.open_chat(self.store.chats()[min(self.selected,count-1)])
                elif self.screen == 'nodes' and count:
                    node = self.nodes()[self.selected]
                    if node.get('adv_type') == 2:
                        self.repeater=node
                        self.screen='repeater'
                        self.repeater_state='confirm'
                        self.repeater_choice=0
                        self.repeater_password=''
                        self.repeater_stats={};self.repeater_clock=None;self.repeater_error=''
                        return
                    if node.get('adv_type') != 1:
                        self.notice('Choose a chat node to send a DM')
                        return
                    cid = self.store.dm(node['public_key'], node['name'])
                    self.open_chat(next(c for c in self.store.chats() if c['id'] == cid))
                elif self.screen == 'settings':
                    if self.selected == 0:
                        self.screen='regions'
                        self.region_catalog=None
                        keys=list(self.region_choices());current=self.store.get('region','US')
                        self.selected=keys.index(current) if current in keys else 0
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
                    elif self.selected == 5:
                        self.store.set('message_sound', 'off' if self.store.get('message_sound','on') == 'on' else 'on')
                    elif self.selected == 6:
                        self.identity_ui.open()
                    elif self.selected == 7:
                        self.backup_ui.open()
                    elif self.selected == 8:
                        self.map_ui.open_sharing()
                    elif self.selected == 9:
                        self.protocol_ui.open()
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
                if self.screen == 'name':
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
        limit=16 if getattr(self.backend,'region','US')=='JP' else 150
        if len(text.encode()) + overhead > limit:
            raise ValueError(f'Max {max(0,limit-overhead)} bytes for this conversation')
        async def work():
            try:
                await self.backend.send(chat, text)
            except Exception as exc:
                if self.store.db.execute('SELECT 1 FROM chats WHERE id=?',(chat['id'],)).fetchone():
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

    def draw_startup_update(self):
        from . import __version__
        image=Image.new('RGB',(320,170),BG)
        draw=ImageDraw.Draw(image)
        def text(x,y,value,color=TEXT,size=12,bold=False):
            self.text.draw(image,(x,y),value,color,size,bold,300)
        text(12,12,'Update available',size=16,bold=True)
        text(12,43,'Installed: '+__version__,MUTED,11)
        text(12,63,'Latest: '+self.startup_release[0],ACCENT,12,True)
        text(12,87,'Update MeshCore now?',size=12)
        for i,(x,label) in enumerate(((12,'Update'),(166,'Later'))):
            selected=i==self.startup_update_choice
            draw.rounded_rectangle((x,113,x+141,141),5,fill=SELECT if selected else PANEL,
                outline=ACCENT if selected else PANEL)
            width=self.text.width(label,12,selected)
            text(x+(142-width)/2,119,label,ACCENT if selected else TEXT,12,selected)
        text(12,153,'Tab / arrows choose   Enter select   Esc later',MUTED,9)
        return image

    def render(self):
        if self.launch_state:
            return self.draw_launch_notice()
        if self.startup_release:
            return self.draw_startup_update()
        if self.screen=='join':return self.join_ui.draw()
        if self.screen in ('map','map_position','map_details','gps_sharing'):return self.map_ui.draw()
        if self.screen=='backup':return self.backup_ui.draw()
        if self.screen=='protocol':return self.protocol_ui.draw()
        if self.screen=='channel_options':return self.channel_ui.draw()
        if self.screen=='identity':return self.identity_ui.draw()
        if self.leave_target:return self.draw_leave()
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
            if not chats:text(10,55,'No conversations · Tab to Join',MUTED,12)
            self.selected = min(self.selected, max(0,len(chats)-1))
            start = max(0,self.selected-3)
            for i, chat in enumerate(chats[start:start+4],start):
                y = 23 + (i-start)*32
                selected = i == self.selected and self.menu < 0
                d.rounded_rectangle((5,y,314,y+30),4,fill=SELECT if selected else PANEL)
                if selected:
                    d.rounded_rectangle((5,y+4,7,y+26),1, fill=ACCENT)
                from .channels import channel_type
                typ=channel_type(chat)
                if typ=='private':
                    # Vector lock is legible even when a font lacks the glyph.
                    d.arc((16,y+3,20,y+9),180,360,fill=ACCENT,width=1)
                    d.line((16,y+6,16,y+8),fill=ACCENT)
                    d.line((20,y+6,20,y+8),fill=ACCENT)
                    d.rounded_rectangle((14,y+7,22,y+14),1,outline=ACCENT,width=1)
                    d.line((18,y+9,18,y+11),fill=ACCENT)
                elif typ=='public':draw_globe(d,13,y+3,12,ACCENT)
                else:text(13,y+1,'@' if typ=='dm' else '#',ACCENT,14,True)
                left=30
                display=chat['name'].lstrip('#') if typ=='hashtag' else chat['name']
                text(left,y+1,display+(' · muted' if chat.get('muted') else ''),size=12,bold=True,width=270-left)
                if chat['unread']:
                    text(284,y+1,str(chat['unread']),ACCENT,10,width=25)
                preview = chat['preview'] or ('Say hello to the mesh' if chat['id']=='public' else 'No messages yet')
                if chat['status'] in ('failed','unconfirmed','sending','interrupted'):
                    preview = chat['status'].capitalize() + ' · ' + preview
                text(left,y+17,preview,MUTED,10,width=302-left)
            if chats and chats[self.selected]['kind']=='channel':hint='Tab menu  ↑↓ select  Enter open  Backspace options'
        elif self.screen == 'name':
            text(10,27,'Your node name',size=14,bold=True)
            text(10,49,'Shown to other people on the mesh.',MUTED,10)
            d.rounded_rectangle((8,74,311,99),4,fill=SELECT)
            text(15,78,(self.draft or 'Your name')+'|',ACCENT,13,width=287)
            text(10,109,'Enter saves your name.',MUTED,10)
            hint='Enter save    Esc back'
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
                kind={1:'Chat',2:'Repeater',3:'Room server'}.get(node.get('adv_type'),'Node')
                text(12,y+18,kind+' · '+node['public_key'][:12],MUTED,10)
            hint = '↑↓ select    Enter open    Esc back'
        elif self.screen == 'repeater':
            text(10,25,self.repeater.get('name','Repeater'),size=13,bold=True,width=300)
            if self.repeater_state in ('confirm','save'):
                saving=self.repeater_state=='save'
                text(10,56,'Save password?' if saving else 'Request Status?',size=14,bold=True)
                saved=self.repeater_passwords.get(self.repeater['public_key']) is not None
                detail='Save on this device after a successful request.' if saving else 'Saved password will be used.' if saved else 'Authenticate to read this repeater.'
                text(10,79,detail,MUTED,10,width=300)
                for i,(x,label) in enumerate(((10,'Yes'),(168,'No'))):
                    selected=i==self.repeater_choice
                    d.rounded_rectangle((x,108,x+140,137),4,fill=SELECT if selected else PANEL,outline=ACCENT if selected else PANEL)
                    text(x+(140-self.text.width(label,12,selected))/2,114,label,ACCENT if selected else TEXT,12,selected)
                hint='Tab / arrows choose   Enter select' if saving or not saved else 'Enter request   Backspace forget   Esc back'
            elif self.repeater_state=='password':
                text(10,57,'Repeater password',size=12,bold=True)
                d.rounded_rectangle((8,80,311,105),4,fill=SELECT)
                text(15,84,'•'*len(self.repeater_password)+'|',ACCENT,13,width=287)
                text(10,119,'Next: choose whether to save locally',MUTED,10)
                hint='Enter continue    Esc cancel'
            elif self.repeater_state=='busy':
                text(10,59,'Authenticating / requesting status…',size=12,width=300)
                text(10,85,'Waiting for the repeater to reply.',MUTED,11)
                hint='Esc cancel'
            elif self.repeater_state=='error':
                text(10,57,'Request failed',size=14,bold=True)
                text(10,84,self.repeater_error,MUTED,11,width=300)
                hint='Enter retry    Esc back'
            else:
                from .repeater import status_lines
                for i,(label,value) in enumerate(status_lines(self.repeater_stats,self.repeater_clock)):
                    y=47+i*19
                    text(10,y,label,MUTED,10,width=85)
                    text(98,y,value,TEXT,10,width=214)
                text(10,143,'*Estimated for single-cell Li-ion; voltage reported',MUTED,8,width=300)
                hint='Enter request again   Backspace forget   Esc back'
        elif self.screen == 'regions':
            regions=list(self.region_choices())
            start=max(0,self.selected-3)
            for i,region in enumerate(regions[start:start+4],start):
                entry=self.region_choices()[region];cfg=dict(entry['radio'])
                cfg['coding_rate']=int(self.store.get('coding_rate_'+region,cfg['coding_rate']))
                path_size=int(self.store.get('path_bytes_'+region,entry['path_bytes']))
                y=23+(i-start)*32
                d.rounded_rectangle((5,y,314,y+30),4,fill=SELECT if i==self.selected else PANEL)
                label=entry['title']+(' · experimental' if region=='JP' else '')
                if region=='SCO':
                    from .regions import protocol_config
                    scope,size=protocol_config(self.store,region)
                    label+=f' · {scope or "unscoped"} / {size}B'
                text(12,y+1,label,bold=True,width=292)
                from .preset_catalog import supported
                detail=(f"{cfg['frequency']/1e6:.3f} MHz SF{cfg['spreading_factor']} BW{cfg['bandwidth']/1000:g} CR4/{cfg['coding_rate']} {path_size}B" if supported(entry) else f"{cfg['frequency']/1e6:g} MHz · outside CAP band")
                text(12,y+18,detail,MUTED,9,width=292)
            hint='↑↓ select   Enter save   R refresh   Esc back'
        elif self.screen == 'settings':
            cr = radio_config(self.store)['coding_rate']
            from .preset_catalog import selected_profile
            labels=['Region: '+selected_profile(self.store,self.store.get('region','US'))['title']+'  (restart to apply)', f'Coding rate: 4/{cr}  (restart to apply)', 'Name: '+self.store.get('name','MeshCore Zero'), 'Announce this node', 'Update app', 'Message sound: '+self.store.get('message_sound','on').title(), 'Identity: import / export', 'Backup / restore', 'GPS broadcasting: '+self.store.get('gps_broadcast','off').title(), 'Scope / path hash']
            start=max(0,self.selected-4)
            for i in range(start,min(len(labels),start+5)):
                label=labels[i]
                y=23+(i-start)*22
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
            elif self.update_state == 'busy' and self.update_started:
                now=time.monotonic()
                elapsed=max(0,now-self.update_stage_started)
                fraction=None
                if self.update_total and self.update_done is not None:
                    fraction=max(0,min(1,self.update_done/self.update_total))
                if self.update_stage=='download' and self.update_done is not None:
                    detail=f'{self.update_done/1048576:.1f}'
                    detail+=(f' / {self.update_total/1048576:.1f} MiB' if self.update_total else ' MiB received')
                    if fraction is not None:detail+=f' · {fraction:.0%}'
                    text(10,98,detail,ACCENT,11,width=300)
                elif fraction is not None:text(10,98,f'{fraction:.0%}',ACCENT,11)
                d.rounded_rectangle((10,116,309,124),3,fill=PANEL)
                if fraction is not None:
                    if fraction>0:d.rounded_rectangle((10,116,10+max(2,int(299*fraction)),124),3,fill=ACCENT)
                else:
                    x=10+int(now*40)%230
                    d.rounded_rectangle((x,116,x+69,124),3,fill=ACCENT)
                text(10,134,f'Stage: {int(elapsed)}s · Total: {int(now-self.update_started)}s',MUTED,9,width=300)
            hint = ('Enter download   Esc back' if self.update_state=='available' else
                    'Enter install   Esc back' if self.update_state=='password' else
                    'Please wait…' if self.update_state=='busy' else 'Enter check again   Esc back')
        elif self.screen == 'chat':
            from .regions import active_scope
            row=self.store.db.execute('SELECT scope FROM chats WHERE id=?',(self.chat['id'],)).fetchone()
            scope=(row[0] or active_scope(self.store,self.backend)) if row and self.chat['kind']=='channel' else None
            from .channels import channel_type
            typ=channel_type(self.chat);left=9
            if typ=='private':
                d.arc((10,24,16,32),180,360,fill=ACCENT,width=1)
                d.rounded_rectangle((8,29,18,35),1,outline=ACCENT)
                d.line((13,31,13,33),fill=ACCENT);left=23
            elif typ=='public':draw_globe(d,9,25,10,ACCENT);left=24
            title=self.chat['name']
            text(left,23,title,ACCENT,11,True,width=(195 if scope else 300)-(left-9))
            if scope:text(207,24,'Scope: '+scope,MUTED,9,width=106)
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

    def draw_leave(self):
        img=Image.new('RGB',(320,170),BG);d=ImageDraw.Draw(img);self.draw_tabs(img)
        def text(x,y,value,color=TEXT,size=11,bold=False):self.text.draw(img,(x,y),value,color,size,bold,width=300)
        text(10,30,'Leave '+self.leave_target['name']+'?',size=14,bold=True)
        text(10,62,'Removes this channel and its saved',MUTED)
        text(10,79,'messages from this device.',MUTED)
        for i,(x,label) in enumerate(((8,'Leave'),(166,'Cancel'))):
            selected=i==self.leave_choice
            d.rounded_rectangle((x,113,x+145,142),4,fill=SELECT if selected else PANEL,outline=ACCENT if selected else PANEL)
            text(x+(145-self.text.width(label,11,selected))/2,120,label,ACCENT if selected else TEXT,11,selected)
        text(8,157,'Tab choose   Enter select   Esc cancel',MUTED,9)
        self.draw_notice(img)
        return img

    def draw_launch_notice(self):
        img=Image.new('RGB',(320,170),BG)
        d=ImageDraw.Draw(img)
        self.text.draw(img,(12,9),'MeshCore',ACCENT,14,True,width=296)
        if self.launch_state=='conflict':
            lines=['MeshZero is running in the background.',
                   'Close it before using the LoRa CAP.',
                   'SSH: sudo systemctl stop meshzero.service',
                   'Okay checks again. Esc exits.']
        elif self.launch_state=='error':
            lines=[self.launch_error,'The radio has not been started.',
                   'Check MeshZero, then reopen this app.']
        else:
            lines=['Checking the radio service…']
        for i,line in enumerate(lines):
            self.text.draw(img,(12,35+i*19),line,TEXT,11,width=296)
        if self.launch_state in ('conflict','error'):
            d.rounded_rectangle((108,124,211,151),4,fill=SELECT,outline=ACCENT)
            width=self.text.width('Okay',12,True)
            self.text.draw(img,((320-width)/2,129),'Okay',ACCENT,12,True,width=96)
        return img

    def active_tab(self):
        if self.screen in ('inbox','chat','channel_options'): return 0
        if self.screen == 'join': return 1
        if self.screen in ('nodes','repeater'): return 2
        if self.screen in ('map','map_position','map_details'): return 3
        return 4

    def draw_tabs(self,img):
        d=ImageDraw.Draw(img)
        d.rectangle((0,0,319,20),fill=PANEL)
        active=self.active_tab()
        for i,title in enumerate(TAB_TITLES):
            left=i*58
            selected=i==active
            bounds=(left+3,2,left+55,18)
            if selected: d.rounded_rectangle(bounds,3,fill=SELECT)
            if i==self.menu: d.rounded_rectangle(bounds,3,outline=ACCENT)
            width=self.text.width(title,9,selected)
            self.text.draw(img,(left+(58-width)/2,3),title,
                ACCENT if selected else MUTED,9,selected,width=52)
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
