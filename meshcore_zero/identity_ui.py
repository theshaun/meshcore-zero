"""Private identity import/export screens; key bytes never enter rendered text."""
from pathlib import Path
from PIL import Image,ImageDraw
from . import identity_keys as keys

class IdentityUI:
    def __init__(self,ui):
        self.ui=ui;self.state='menu';self.selected=0;self.choice=1
        self.input='';self.candidate=None;self.preview='';self.operation='import';self.export_path=None
        self.root=Path(ui.store.db.execute('PRAGMA database_list').fetchone()[2]).parent

    def clear(self):
        self.input='';self.candidate=None;self.preview=''

    def open(self):
        self.clear();self.state='menu';self.selected=0;self.ui.screen='identity'

    def render_key(self):
        return (self.state,self.selected,self.choice,len(self.input),self.input if self.state=='file' else None,self.preview,self.operation,str(self.export_path))

    def stage(self,raw,operation='import'):
        self.candidate=raw;self.preview=keys.public_key(raw);self.operation=operation
        self.input='';self.state='confirm';self.choice=1

    async def key(self,key):
        if self.state=='applying':return
        if key=='escape':
            if self.state=='menu':self.ui.screen='settings';self.ui.selected=6
            else:self.state='menu'
            self.clear();return
        if self.state in ('confirm','export_confirm'):
            if key in ('tab','left','right','up','down'):self.choice=1-self.choice
            elif key=='enter':
                if self.choice==1:self.clear();self.state='menu';return
                if self.state=='export_confirm':
                    try:self.export_path=keys.export_key(self.ui.store);self.state='export_done'
                    except Exception:self.ui.notice('Could not export identity file')
                else:
                    try:
                        changed=keys.replace_identity(self.ui.store,self.candidate)
                        self.clear()
                        if changed:
                            self.state='applying';self.ui.restart_requested=True;self.ui.running=False
                        else:self.state='menu';self.ui.notice('This identity is already active')
                    except ValueError as exc:self.ui.notice(str(exc))
                    except Exception:self.ui.notice('Could not replace identity')
            return
        if key=='tab':
            self.clear();self.ui.switch_tab(0);return
        if self.state=='menu':
            if key in ('up','down'):self.selected=max(0,min(3,self.selected+(1 if key=='down' else -1)))
            elif key=='enter':
                self.clear()
                if self.selected==0:self.state='input'
                elif self.selected==1:self.state='file';self.input=str(self.root/'identity-import.txt')
                elif self.selected==2:self.state='export_confirm';self.choice=1
                else:
                    backup=self.ui.store.get('identity_backup')
                    if backup is None:self.ui.notice('No previous identity backup')
                    else:
                        try:self.stage(keys.stored_key(backup),'restore')
                        except ValueError as exc:self.ui.notice(str(exc))
        elif self.state in ('input','file'):
            if key=='backspace':self.input=self.input[:-1]
            elif key=='enter':
                try:self.stage(keys.parse_firmware(self.input) if self.state=='input' else keys.read_key_file(self.input))
                except ValueError as exc:self.ui.notice(str(exc))
                except OSError:self.ui.notice('Cannot read key file · check path')
            elif len(key)==1 and key.isprintable():
                if self.state=='input':
                    if key in '0123456789abcdefABCDEF' and len(self.input)<128:self.input+=key
                elif len(self.input)<240:self.input+=key
        elif self.state=='export_done' and key=='enter':self.state='menu'

    def draw(self):
        from .ui import BG,TEXT,MUTED,ACCENT,SELECT,PANEL
        ui=self.ui;img=Image.new('RGB',(320,170),BG);d=ImageDraw.Draw(img);ui.draw_tabs(img)
        def text(x,y,value,color=TEXT,size=11,bold=False,width=300):
            return ui.text.draw(img,(x,y),value,color,size,bold,width)
        def buttons(yes):
            for i,(x,label) in enumerate(((8,yes),(166,'Cancel'))):
                active=i==self.choice
                d.rounded_rectangle((x,118,x+145,146),4,fill=SELECT if active else PANEL,outline=ACCENT if active else PANEL)
                text(x+(145-ui.text.width(label,11,active))/2,124,label,ACCENT if active else TEXT,11,active)
        hint='Esc back'
        if self.state=='menu':
            text(10,25,'Identity',size=13,bold=True)
            try:public=keys.public_key(keys.stored_key(ui.store.get('identity')))
            except ValueError:public='Identity not initialized'
            text(10,44,public[:32],MUTED,9);text(10,56,public[32:],MUTED,9)
            for i,label in enumerate(('Import firmware key','Import from file','Export firmware key','Restore previous identity')):
                y=74+i*19;d.rounded_rectangle((5,y,314,y+17),3,fill=SELECT if i==self.selected else PANEL)
                text(12,y+1,label,size=10)
            hint='↑↓ select   Enter open   Esc back'
        elif self.state=='input':
            text(10,28,'Import firmware key',size=13,bold=True)
            text(10,54,'128 hexadecimal characters',MUTED,10)
            d.rounded_rectangle((8,75,311,101),4,fill=SELECT)
            text(15,79,'•'*min(34,len(self.input))+'|',ACCENT,12)
            text(10,114,f'{len(self.input)} / 128 characters',MUTED,10)
            hint='Enter preview   Esc cancel'
        elif self.state=='file':
            text(10,28,'Import key file',size=13,bold=True)
            text(10,53,'Text file containing a 128-character key.',MUTED,10)
            d.rounded_rectangle((8,76,311,102),4,fill=SELECT)
            display=self.input if len(self.input)<44 else '…'+self.input[-43:]
            text(14,81,display+'|',ACCENT,10,width=292)
            hint='Edit path   Enter preview   Esc cancel'
        elif self.state=='confirm':
            text(10,27,'Restore identity?' if self.operation=='restore' else 'Replace identity?',size=13,bold=True)
            text(10,50,'New public key:',MUTED,10)
            text(10,65,self.preview[:32],ACCENT,10);text(10,79,self.preview[32:],ACCENT,10)
            text(10,99,'Previous key backed up · restart to apply',MUTED,9)
            buttons('Restore' if self.operation=='restore' else 'Import');hint='Tab choose   Enter select   Esc cancel'
        elif self.state=='export_confirm':
            text(10,28,'Export private key?',size=13,bold=True)
            text(10,58,'Writes identity-export.txt to app data.',MUTED,10)
            text(10,80,'Keep this file secret.',ACCENT,11,bold=True)
            text(10,99,'Firmware format · 128 hexadecimal characters',MUTED,9)
            buttons('Export');hint='Tab choose   Enter select   Esc cancel'
        elif self.state=='export_done':
            text(10,28,'Identity exported',size=13,bold=True)
            text(10,58,'Private file saved with owner-only access.',MUTED,10)
            path=str(self.export_path)
            if path.startswith(str(Path.home())):path='~'+path[len(str(Path.home())):]
            for i in range(0,len(path),44):text(10,82+i//44*13,path[i:i+44],ACCENT,9)
            hint='Enter / Esc back'
        else:text(10,60,'Restarting with the selected identity…',size=11)
        text(8,157,hint,MUTED,9);ui.draw_notice(img)
        return img
