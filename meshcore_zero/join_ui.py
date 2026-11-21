"""Channel-type picker and masked shared-key entry."""
from PIL import Image,ImageDraw
from .channels import join_private
class JoinUI:
    TYPES=('Hashtag','Private','Public')
    def __init__(self,ui):self.ui=ui;self.type=0;self.field=0;self.private_name='';self.secret=''
    def clear_secret(self):self.secret=''
    def render_key(self):return (self.type,self.field,self.private_name,len(self.secret))
    def fields(self):return 4 if self.type==1 else 2 if self.type==2 else 3
    def change_type(self,step):self.type=(self.type+step)%3;self.field=0;self.clear_secret()
    def submit(self):
        u=self.ui
        try:
            cid=(u.store.join(u.draft) if self.type==0 else join_private(u.store,self.private_name,self.secret) if self.type==1 else u.store.join_public())
            if u.backend:u.backend.sync_channels()
            self.clear_secret();u.open_chat(next(c for c in u.store.chats() if c['id']==cid))
        except (ValueError,RuntimeError) as exc:u.notice(str(exc))
    async def key(self,key):
        u=self.ui
        if key=='tab':self.clear_secret();u.switch_tab(2);return
        if key=='escape':self.clear_secret();u.switch_tab(0);return
        if key in ('up','down'):self.field=max(0,min(self.fields()-1,self.field+(1 if key=='down' else -1)));return
        if self.field==0 and key in ('left','right'):
            self.change_type(-1 if key=='left' else 1);return
        if key=='enter':
            if self.field==0:self.field=1;return
            if self.type==2 or self.type==0:self.submit()
            elif self.field<3:self.field+=1
            else:self.submit()
            return
        if len(key)==1 and key.isprintable() and self.field==0 and self.type!=2:self.field=1
        if self.type==0 and self.field==1:
            if key=='backspace':u.draft=u.draft[:-1] if len(u.draft)>1 else '#'
            elif len(key)==1 and key.isprintable() and len((u.draft+key).encode())<=31:
                if not(key=='#' and u.draft=='#'):u.draft+=key
            u.join_draft=u.draft
        elif self.type==1 and self.field==1:
            if key=='backspace':self.private_name=self.private_name[:-1]
            elif len(key)==1 and key.isprintable() and len((self.private_name+key).encode())<=32:self.private_name+=key
        elif self.type==1 and self.field==2:
            if key=='backspace':self.secret=self.secret[:-1]
            elif len(key)==1 and key.isascii() and key.isprintable() and len(self.secret)<96:self.secret+=key
    def draw(self):
        from .ui import BG,TEXT,MUTED,ACCENT,SELECT,PANEL
        u=self.ui;img=Image.new('RGB',(320,170),BG);d=ImageDraw.Draw(img);u.draw_tabs(img)
        def text(x,y,s,color=TEXT,size=11,bold=False,width=300):u.text.draw(img,(x,y),s,color,size,bold,width=width)
        def box(y,index):d.rounded_rectangle((7,y,312,y+24),4,fill=SELECT if self.field==index else PANEL)
        box(26,0);text(14,31,'Type: '+self.TYPES[self.type],ACCENT,11,True);text(264,31,'←  →',MUTED,11)
        if self.type==1:
            box(62,1);text(14,67,(self.private_name or 'Channel name')+('|' if self.field==1 else ''),TEXT if self.private_name else MUTED,11,width=290)
            text(10,91,f'Shared key · {len(self.secret)} chars · Hex / Base64',MUTED,9)
            box(103,2);text(14,108,'•'*min(29,len(self.secret))+('|' if self.field==2 else ''),ACCENT,11,width=287)
            d.rounded_rectangle((7,133,312,152),4,fill=SELECT if self.field==3 else PANEL);text(118,135,'Join private',ACCENT,10,True)
        elif self.type==0:
            text(10,58,'Public topic · key comes from its name',MUTED,9)
            box(77,1);text(14,82,u.draft+('|' if self.field==1 else ''),ACCENT,12,width=287)
            d.rounded_rectangle((7,118,312,144),4,fill=SELECT if self.field==2 else PANEL);text(135,123,'Join',ACCENT,11,True)
        else:
            text(10,63,'The shared Public channel.',MUTED,11)
            text(10,86,'Anyone on the mesh can read its messages.',MUTED,10)
            d.rounded_rectangle((7,118,312,144),4,fill=SELECT if self.field==1 else PANEL);text(110,123,'Join / open Public',ACCENT,11,True)
        text(6,158,'↑↓ fields  ←→ type  Enter continue  Esc back',MUTED,8);u.draw_notice(img);return img
