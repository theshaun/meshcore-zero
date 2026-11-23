"""Small per-profile scope/path editor. Saved changes apply at next startup."""
from PIL import Image,ImageDraw
from .regions import protocol_config,normalize_scope


class ProtocolUI:
    def __init__(self,ui):self.ui=ui;self.selected=0;self.state='menu';self.input='';self.region='US'
    def open(self):
        self.region=self.ui.store.get('region','US');self.selected=0;self.state='menu';self.input='';self.ui.screen='protocol'
    def render_key(self):return self.region,self.selected,self.state,self.input
    async def key(self,key):
        u=self.ui
        if self.state=='scope':
            if key=='escape':self.state='menu';self.input=''
            elif key=='backspace':self.input=self.input[:-1]
            elif key=='enter':
                try:
                    scope=normalize_scope(self.input)
                    u.store.set('scope_'+self.region,scope)
                    self.state='menu';self.input='';u.notice('Scope saved · restart to apply')
                except ValueError as exc:u.notice(str(exc))
            elif len(key)==1 and key.isprintable() and len(self.input)<31:self.input+=key
            return
        if key in ('escape','backspace'):u.screen='settings';u.selected=9;return
        if key=='tab':u.switch_tab(0);return
        if key in ('up','down'):self.selected=max(0,min(2,self.selected+(1 if key=='down' else -1)))
        elif self.selected==1 and key in ('enter','left','right'):
            size=protocol_config(u.store,self.region)[1]
            size=(size-1+(-1 if key=='left' else 1))%3+1
            u.store.set('path_bytes_'+self.region,size);u.notice('Path size saved · restart to apply')
        elif key=='enter':
            if self.selected==0:self.state='scope';self.input=protocol_config(u.store,self.region)[0]
            elif self.selected==2:
                with u.store.db:u.store.db.execute('DELETE FROM settings WHERE key IN (?,?)',('scope_'+self.region,'path_bytes_'+self.region))
                u.notice('Preset restored · restart to apply')
    def draw(self):
        from .ui import BG,TEXT,MUTED,ACCENT,SELECT,PANEL
        u=self.ui;img=Image.new('RGB',(320,170),BG);d=ImageDraw.Draw(img);u.draw_tabs(img)
        def text(x,y,s,color=TEXT,size=11,bold=False):u.text.draw(img,(x,y),s,color,size,bold,width=300)
        text(10,27,'Scope / path hash',size=14,bold=True)
        from .preset_catalog import selected_profile
        title=selected_profile(u.store,self.region)['title']
        text(10,49,title+' · restart app to apply',MUTED,10)
        if self.state=='scope':
            text(10,73,'Region scope · blank = unscoped',MUTED,11)
            d.rounded_rectangle((8,96,311,124),4,fill=SELECT)
            text(14,102,self.input+'|',ACCENT,12)
            text(10,133,'Use the scope agreed by your local mesh.',MUTED,10)
            hint='Enter save   Backspace edit   Esc cancel'
        else:
            scope,size=protocol_config(u.store,self.region)
            labels=['Region scope: '+(scope or 'Unscoped'),f'Path hash: {size} '+('byte' if size==1 else 'bytes'),'Reset to region preset']
            for i,label in enumerate(labels):
                y=69+i*25;d.rounded_rectangle((5,y,314,y+22),4,fill=SELECT if i==self.selected else PANEL);text(12,y+4,label)
            hint='↑↓ select   Enter change   Esc back'
        text(8,157,hint,MUTED,9);u.draw_notice(img);return img
