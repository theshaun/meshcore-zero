"""Encrypted backup screens; secrets never appear in render keys or text."""
import asyncio
from pathlib import Path
import time
from PIL import Image,ImageDraw
from . import backup
class BackupUI:
    def __init__(self,ui):
        self.ui=ui;self.root=backup.root_for(ui.store);self.state='menu';self.selected=0;self.input='';self.password='';self.data=None;self.info={};self.path='';self.choice=1;self.files=[];self.action='';self.started=0;self.result=''
    def clear(self):self.input='';self.password='';self.data=None;self.info={}
    def open(self):self.clear();self.state='menu';self.selected=0;self.ui.screen='backup'
    def render_key(self):return (self.state,self.selected,len(self.input),self.input if self.state=='path' else '',str(self.path),self.choice,self.result,int(time.monotonic()-self.started) if self.state=='busy' else None,repr(self.info))
    def start(self,action):
        self.action=action;self.state='busy';self.started=time.monotonic()
        task=asyncio.create_task(self.work(action));self.ui.tasks.add(task);task.add_done_callback(self.ui.tasks.discard)
    async def work(self,action):
        try:
            if action=='export':
                self.path=await asyncio.to_thread(backup.export,self.root,self.password)
                self.clear();self.state='done'
            else:
                self.data=await asyncio.to_thread(backup.read,self.path,self.password)
                self.info=backup.summary(self.data);self.input='';self.state='confirm';self.choice=1
        except Exception as exc:
            self.clear();self.state='menu';self.selected=0
            self.ui.notice(str(exc) if isinstance(exc,ValueError) else 'Could not read or write backup')
    async def key(self,key):
        if self.state=='busy':return
        if key=='escape':
            if self.state=='menu':self.ui.screen='settings';self.ui.selected=7
            else:self.state='menu';self.selected=0
            self.clear();return
        if self.state=='confirm':
            if key in ('tab','left','right','up','down'):self.choice=1-self.choice
            elif key=='enter':
                if self.choice==1:self.clear();self.state='menu'
                else:
                    self.ui.pending_restore=(self.data,self.password);self.clear()
                    self.state='restoring';self.ui.restart_requested=True;self.ui.running=False
            return
        if self.state in ('password','repeat'):
            if key=='backspace':self.input=self.input[:-1]
            elif key=='enter':
                if self.state=='repeat':
                    if self.input!=self.password:self.input='';self.ui.notice('Passwords do not match');return
                    self.input='';self.start('export')
                else:
                    if not 8<=len(self.input)<=128:self.ui.notice('Use 8–128 characters');return
                    self.password=self.input;self.input=''
                    if self.action=='export':self.state='repeat'
                    else:self.start('read')
            elif len(key)==1 and key.isprintable() and len(self.input)<128:self.input+=key
            return
        if key=='tab':self.clear();self.ui.switch_tab(0);return
        if self.state=='menu':
            if key in ('up','down'):self.selected=1-self.selected
            elif key=='enter':
                self.clear()
                if self.selected==0:self.action='export';self.state='password'
                else:
                    self.files=sorted((self.root/'backups').glob('*.mczb'),reverse=True)[:1000]
                    self.selected=0;self.state='files'
        elif self.state=='files':
            if key in ('up','down'):self.selected=max(0,min(len(self.files),self.selected+(1 if key=='down' else -1)))
            elif key=='enter':
                if self.selected==len(self.files):self.state='path';self.input=str(self.root/'backups'/'')
                else:self.path=self.files[self.selected];self.action='read';self.state='password'
        elif self.state=='path':
            if key=='backspace':self.input=self.input[:-1]
            elif key=='enter':self.path=self.input;self.input='';self.action='read';self.state='password'
            elif len(key)==1 and key.isprintable() and len(self.input)<512:self.input+=key
        elif self.state in ('done','result') and key=='enter':self.state='menu';self.selected=0
    def draw(self):
        from .ui import BG,TEXT,MUTED,ACCENT,SELECT,PANEL
        u=self.ui;img=Image.new('RGB',(320,170),BG);d=ImageDraw.Draw(img);u.draw_tabs(img)
        def text(x,y,s,color=TEXT,size=11,bold=False):u.text.draw(img,(x,y),s,color,size,bold,width=300)
        text(10,27,'Backup / restore',size=14,bold=True);hint='Esc back'
        if self.state=='menu':
            for i,label in enumerate(('Create encrypted backup','Restore encrypted backup')):
                y=59+i*29;d.rounded_rectangle((5,y,314,y+25),4,fill=SELECT if i==self.selected else PANEL);text(12,y+5,label)
            text(10,123,'Includes identity, chats and saved passwords.',MUTED,9)
            hint='↑↓ choose   Enter open   Esc back'
        elif self.state in ('password','repeat'):
            text(10,55,'Confirm backup password' if self.state=='repeat' else ('New backup password' if self.action=='export' else 'Enter backup password'),size=12,bold=True)
            text(10,78,'8–128 characters · keep this password safe',MUTED,9)
            d.rounded_rectangle((8,99,311,126),4,fill=SELECT);text(15,104,'•'*min(33,len(self.input))+'|',ACCENT,12)
            hint='Enter continue   Esc cancel'
        elif self.state=='files':
            labels=[p.name for p in self.files]+['Other file…']
            start=max(0,self.selected-3)
            for i in range(start,min(len(labels),start+4)):
                y=53+(i-start)*23;d.rounded_rectangle((5,y,314,y+21),4,fill=SELECT if i==self.selected else PANEL);text(12,y+4,labels[i],size=9)
            hint='↑↓ select file   Enter open   Esc back'
        elif self.state=='path':
            text(10,58,'Backup file path',size=12,bold=True)
            text(10,87,'Copy .mczb files to the backups folder via SSH.',MUTED,9)
            d.rounded_rectangle((8,108,311,134),4,fill=SELECT);text(15,113,('…'+self.input[-43:] if len(self.input)>44 else self.input)+'|',ACCENT,9)
            hint='Enter continue   Esc cancel'
        elif self.state=='confirm':
            text(10,51,f"{self.info['channels']} channels · {self.info['messages']} messages · {self.info['contacts']} nodes",MUTED,10)
            public=self.info['public_key'];text(10,68,public[:32],ACCENT,9);text(10,80,public[32:],ACCENT,9)
            text(10,96,'Replaces all app data and radio settings.',MUTED,9)
            text(10,108,'Saves encrypted recovery backup, then restarts.',MUTED,9)
            for i,(x,label) in enumerate(((8,'Restore'),(166,'Cancel'))):
                active=i==self.choice;d.rounded_rectangle((x,124,x+145,149),4,fill=SELECT if active else PANEL,outline=ACCENT if active else PANEL);text(x+47,129,label,ACCENT if active else TEXT,11,active)
            hint='Tab choose   Enter select   Esc cancel'
        elif self.state=='busy':
            text(10,64,'Encrypting backup…' if self.action=='export' else 'Unlocking and validating…',size=12,bold=True)
            text(10,91,f'{int(time.monotonic()-self.started)} seconds',MUTED,11)
        elif self.state=='restoring':
            text(10,62,'Saving recovery backup and restoring…',size=11,bold=True);text(10,89,'Please keep the device powered on.',MUTED,10)
        elif self.state=='result':
            text(10,62,self.result,size=12,bold=True);hint='Enter / Esc back'
        else:
            text(10,54,'Encrypted backup saved',size=12,bold=True)
            path=str(self.path).replace(str(Path.home()),'~',1)
            for i in range(0,len(path),45):text(10,79+i//45*13,path[i:i+45],ACCENT,9)
            text(10,132,'Copy it off-device; the password is not saved.',MUTED,9)
            hint='Enter / Esc back'
        text(8,157,hint,MUTED,9);u.draw_notice(img);return img
