"""Channel actions and an optional scope override; default behavior stays simple."""
from PIL import Image,ImageDraw
class ChannelUI:
    def __init__(self,ui):self.ui=ui;self.chat=None;self.selected=0;self.state='menu';self.choice=1;self.input=''
    def open(self,chat):
        self.chat=dict(chat);self.selected=0;self.state='menu';self.choice=1;self.input='';self.ui.screen='channel_options'
    def row(self):return self.ui.store.db.execute('SELECT * FROM chats WHERE id=?',(self.chat['id'],)).fetchone()
    def render_key(self):return (self.chat['id'] if self.chat else None,self.selected,self.state,self.choice,self.input)
    async def key(self,key):
        u=self.ui
        if self.state=='clear':
            if key=='escape' or key=='enter' and self.choice==1:self.state='menu'
            elif key in ('tab','up','down','left','right'):self.choice=1-self.choice
            elif key=='enter':
                if u.backend and u.backend.send_lock.locked():u.notice('Radio busy · try again after sending');return
                u.store.clear_history(self.chat['id']);self.state='menu';u.notice('Channel history cleared')
            return
        if self.state=='scope':
            if key=='escape':self.state='menu';return
            if key=='backspace':self.input=self.input[:-1]
            elif key=='enter':
                try:u.store.set_scope(self.chat['id'],self.input);self.state='menu';u.notice('Channel scope saved')
                except ValueError as exc:u.notice(str(exc))
            elif len(key)==1 and key.isprintable() and len(self.input)<31:self.input+=key
            return
        if key in ('escape','backspace'):u.screen='inbox';return
        if key=='tab':u.switch_tab(1);return
        if key in ('up','down'):self.selected=max(0,min(3,self.selected+(1 if key=='down' else -1)))
        elif key=='enter':
            if self.selected==0:u.store.mute(self.chat['id'],not u.store.is_muted(self.chat['id']))
            elif self.selected==1:self.state='scope';self.input=self.row()['scope'] or ''
            elif self.selected==2:self.state='clear';self.choice=1
            else:u.screen='inbox';u.leave_target=self.chat.copy();u.leave_choice=1
    def draw(self):
        from .ui import BG,TEXT,MUTED,ACCENT,SELECT,PANEL
        from .regions import DEFAULT_SCOPES
        u=self.ui;img=Image.new('RGB',(320,170),BG);d=ImageDraw.Draw(img);u.draw_tabs(img)
        def text(x,y,s,color=TEXT,size=11,bold=False):u.text.draw(img,(x,y),s,color,size,bold,width=300)
        text(10,27,self.chat['name'],size=14,bold=True)
        if self.state=='clear':
            text(10,57,'Clear saved messages?',size=13,bold=True);text(10,80,'Keeps this channel joined.',MUTED,11)
            for i,(x,label) in enumerate(((8,'Clear'),(166,'Cancel'))):
                active=i==self.choice;d.rounded_rectangle((x,112,x+145,142),4,fill=SELECT if active else PANEL,outline=ACCENT if active else PANEL)
                text(x+(145-u.text.width(label,11,active))/2,120,label,ACCENT if active else TEXT,11,active)
            hint='Tab choose   Enter select   Esc cancel'
        elif self.state=='scope':
            text(10,54,'Scope override (optional)',size=12,bold=True)
            text(10,76,'Blank = use regional default',MUTED,10)
            d.rounded_rectangle((8,99,311,125),4,fill=SELECT);text(15,105,self.input+'|',ACCENT,12)
            hint='Enter save   Backspace edit   Esc cancel'
        else:
            scope=self.row()['scope'];region=u.backend.region if u.backend and u.backend.engine else u.store.get('region','US');default=DEFAULT_SCOPES.get(region,'unscoped')
            labels=['Unmute notifications' if u.store.is_muted(self.chat['id']) else 'Mute notifications','Scope: '+(scope or 'Default · '+default),'Clear message history','Leave channel']
            for i,label in enumerate(labels):
                y=51+i*24;d.rounded_rectangle((5,y,314,y+21),4,fill=SELECT if i==self.selected else PANEL);text(12,y+3,label)
            hint='↑↓ select   Enter choose   Esc back'
        text(8,157,hint,MUTED,9);u.draw_notice(img);return img
