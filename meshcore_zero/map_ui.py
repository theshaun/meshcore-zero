"""Offline north-up radar; independent implementation using advertised positions."""
import json
import math
import time
from PIL import Image,ImageDraw
from .gps import LAST_FIX_SECONDS

SCALES=(100,250,500,1000,2500,5000,10000,25000,50000,100000,250000,500000,1000000,2500000,5000000,10000000,25000000)
STALE_SECONDS=24*60*60

def position(lat,lon):
    if isinstance(lat,bool) or isinstance(lon,bool):return None
    try:lat=float(lat);lon=float(lon)
    except (TypeError,ValueError,OverflowError):return None
    return (lat,lon) if math.isfinite(lat) and math.isfinite(lon) and -90<=lat<=90 and -180<=lon<=180 else None

def manual_position(text):
    if not text.strip():return None
    parts=text.split(',')
    point=position(*parts) if len(parts)==2 else None
    if point is None:raise ValueError('Use latitude, longitude (decimal degrees)')
    return point

def distance_bearing(origin,destination):
    a,b=map(math.radians,origin);c,d=map(math.radians,destination)
    delta=d-b
    h=math.sin((c-a)/2)**2+math.cos(a)*math.cos(c)*math.sin(delta/2)**2
    distance=6371008.8*2*math.asin(math.sqrt(max(0,min(1,h))))
    bearing=math.degrees(math.atan2(math.sin(delta)*math.cos(c),math.cos(a)*math.sin(c)-math.sin(a)*math.cos(c)*math.cos(delta)))%360
    return distance,bearing

def distance_text(metres):
    if metres<1000:return f'{metres:.0f} m'
    return f'{metres/1000:.1f} km' if metres<10000 else f'{metres/1000:,.0f} km'

def age_text(seconds):
    if seconds is None:return 'unknown'
    if seconds<60:return 'just now'
    if seconds<3600:return f'{seconds//60:.0f}m ago'
    if seconds<86400:return f'{seconds//3600:.0f}h ago'
    return f'{seconds//86400:.0f}d ago'

def has_position(node):
    point=position(node.get('gps_lat'),node.get('gps_lon'))
    if point is None:return None
    raw=node.get('last_advert_packet')
    if raw:
        try:
            from openhop_core.protocol import Packet
            packet=Packet()
            if not packet.read_from(bytes.fromhex(raw)):return None
            payload=packet.get_payload()
            if packet.get_payload_type()!=4 or len(payload)<109 or not payload[100]&0x10:return None
        except (ValueError,TypeError,IndexError):return None
    elif point==(0.0,0.0):return None  # Legacy default coordinates are not a location report.
    return point

class MapUI:
    def __init__(self,ui):self.ui=ui;self.zoom=None;self.scale_index=5;self.selected_key=None;self.state='radar';self.input='';self.share_choice=1
    def render_key(self):
        active=self.ui.screen in ('map','map_position','map_details','gps_sharing')
        return (self.zoom,self.selected_key,self.state,self.input,self.share_choice,self.ui.gps.revision() if active else None,int(time.time())//60 if active else None)
    def centre(self):
        fix=self.ui.gps.fresh()
        if fix:return (fix.latitude,fix.longitude),'GPS fix'
        last=self.ui.gps.parser.last_fix
        if last and 0<=time.monotonic()-last.updated<=LAST_FIX_SECONDS:return (last.latitude,last.longitude),'Last GPS'
        try:manual=manual_position(self.ui.store.get('map_position',''))
        except ValueError:manual=None
        return (manual,'Manual') if manual else (None,self.ui.gps.status)
    def dots(self,centre):
        result=[]
        own=self.ui.backend.engine.get_public_key().hex() if self.ui.backend and self.ui.backend.engine else None
        # CompanionRadio exposes identity through get_public_key(). Never derive/store GPS in the identity database.
        for node in self.ui.nodes():
            point=has_position(node)
            if point is None or node.get('public_key')==own:continue
            distance,bearing=distance_bearing(centre,point)
            timestamp=node.get('map_position_at',node.get('last_advert_timestamp',0))
            try:
                stamp=float(timestamp);age=max(0,time.time()-stamp) if math.isfinite(stamp) and 0<stamp<=time.time()+300 else None
            except (ValueError,TypeError,OverflowError):age=None
            result.append({'node':node,'distance':distance,'bearing':bearing,'age':age,'stale':age is None or age>STALE_SECONDS})
        return sorted(result,key=lambda p:(p['distance'],p['node'].get('public_key','')))
    def model(self):
        centre,status=self.centre();dots=self.dots(centre) if centre else []
        if self.zoom is None:
            farthest=max((p['distance'] for p in dots),default=5000)
            self.scale_index=next((i for i,s in enumerate(SCALES) if s>=farthest),len(SCALES)-1)
        else:self.scale_index=self.zoom
        if dots and not any(p['node']['public_key']==self.selected_key for p in dots):self.selected_key=dots[0]['node']['public_key']
        return centre,status,dots,SCALES[self.scale_index]
    def open_sharing(self):
        if self.ui.store.get('gps_broadcast','off')=='on':
            self.ui.store.set('gps_broadcast','off')
            if self.ui.backend:self.ui.backend.update_location_policy()
            self.ui.notice('GPS broadcasting off')
        else:self.share_choice=1;self.ui.screen='gps_sharing'
    async def key(self,key):
        u=self.ui
        if u.screen=='gps_sharing':
            if key=='escape' or key=='enter' and self.share_choice==1:u.screen='settings';u.selected=8
            elif key in ('tab','left','right','up','down'):self.share_choice=1-self.share_choice
            elif key=='enter':
                u.store.set('gps_broadcast','on');u.gps.last_broadcast=float('-inf')
                if u.backend:u.backend.update_location_policy()
                u.screen='settings';u.selected=8;u.notice('Sharing enabled · waiting for fresh GPS')
            return
        if u.screen=='map_position':
            if key=='escape':u.screen='map';self.input=''
            elif key=='backspace':self.input=self.input[:-1]
            elif key=='enter':
                try:
                    point=manual_position(self.input)
                    u.store.set('map_position',f'{point[0]:.6f},{point[1]:.6f}' if point else '')
                    self.input='';u.screen='map'
                except ValueError as exc:u.notice(str(exc))
            elif len(key)==1 and key in '0123456789.,-+ ' and len(self.input)<50:self.input+=key
            return
        if u.screen=='map_details':
            if key in ('escape','enter'):u.screen='map'
            elif key=='tab':u.switch_tab(4)
            return
        if key=='tab':u.switch_tab(4);return
        if key=='escape':u.switch_tab(0);return
        _,_,dots,_=self.model()
        if key in ('up','+','='):self.zoom=max(0,self.scale_index-1)
        elif key in ('down','-','_'):self.zoom=min(len(SCALES)-1,self.scale_index+1)
        elif key=='0':self.zoom=None
        elif key in ('left','right') and dots:
            index=next((i for i,p in enumerate(dots) if p['node']['public_key']==self.selected_key),0)
            self.selected_key=dots[(index+(1 if key=='right' else -1))%len(dots)]['node']['public_key']
        elif key in ('m','M'):self.input=u.store.get('map_position','');u.screen='map_position'
        elif key=='enter':
            if dots:u.screen='map_details'
            else:u.notice('No positioned nodes yet')
    def draw(self):
        from .ui import BG,TEXT,MUTED,ACCENT,SELECT,PANEL
        u=self.ui;img=Image.new('RGB',(320,170),BG);d=ImageDraw.Draw(img);u.draw_tabs(img)
        def text(x,y,s,color=TEXT,size=10,bold=False,width=300):return u.text.draw(img,(x,y),s,color,size,bold,width=width)
        if u.screen=='gps_sharing':
            text(10,29,'Share GPS location?',size=14,bold=True)
            text(10,58,'Broadcasts your precise GPS position.',MUTED,11)
            text(10,80,'Fresh fixes only · every 15 minutes.',MUTED,10)
            text(10,98,'Manual positions are never broadcast.',MUTED,10)
            for i,(x,label) in enumerate(((8,'Enable'),(166,'Cancel'))):
                selected=i==self.share_choice;d.rounded_rectangle((x,117,x+145,146),4,fill=SELECT if selected else PANEL,outline=ACCENT if selected else PANEL);text(x+49,124,label,ACCENT if selected else TEXT,11,selected)
            text(8,157,'Tab choose   Enter select   Esc cancel',MUTED,9);return img
        if u.screen=='map_position':
            text(10,29,'Manual fallback position',size=14,bold=True)
            text(10,58,'Latitude, longitude · decimal degrees',MUTED,10)
            text(10,78,'Used without GPS. Blank clears it.',MUTED,10)
            d.rounded_rectangle((8,101,311,129),4,fill=SELECT);text(14,107,self.input+'|',ACCENT,11,width=293)
            text(8,157,'Enter save   Esc cancel · Never broadcast',MUTED,9);u.draw_notice(img);return img
        centre,status,dots,scale=self.model()
        chosen=next((p for p in dots if p['node']['public_key']==self.selected_key),None)
        if u.screen=='map_details':
            if chosen:
                node=chosen['node'];kind={1:'Chat node',2:'Repeater',3:'Room server'}.get(node.get('adv_type'),'Node')
                text(9,27,node.get('name') or node['public_key'][:10],ACCENT,13,True)
                text(9,49,kind+' · '+distance_text(chosen['distance'])+f" · {chosen['bearing']:.0f}°",size=11)
                point=has_position(node);text(9,68,f'{point[0]:.5f}, {point[1]:.5f}',MUTED,10)
                heard=node.get('map_heard_at');age=max(0,time.time()-heard) if isinstance(heard,(int,float)) else None
                text(9,87,'Advert heard: '+age_text(age),size=10)
                text(9,104,'Position: '+age_text(chosen['age'])+(' · older report' if chosen['stale'] else ''),MUTED,10)
                rssi=node.get('map_rssi');snr=node.get('map_snr')
                rx=(f'{rssi:g} dBm / {snr:g} dB' if isinstance(rssi,(int,float)) and isinstance(snr,(int,float)) else 'unavailable')
                text(9,121,'Advert RX: '+rx,MUTED,10)
                text(9,138,'RX describes the last radio leg, possibly a relay.',MUTED,8)
            else:text(10,62,'Position no longer available',MUTED,12)
            text(8,157,'Enter / Esc map   Tab Settings',MUTED,9);return img
        cx,cy,r=160,89,60
        for radius in (r,r//2):d.ellipse((cx-radius,cy-radius,cx+radius,cy+radius),outline='#294354')
        text(cx-3,24,'N',MUTED,9)
        text(7,25,distance_text(scale),MUTED,9);text(7,37,distance_text(scale/2)+' inner',MUTED,9)
        sats=u.gps.parser.satellites
        status_text=(f'GPS · {sats} sats' if sats is not None else status) if status=='GPS fix' else status
        if status=='Waiting for GPS' and sats is not None:status_text=f'{sats} sats · no fix'
        text(236,25,status_text,MUTED,9,width=80)
        sharing=u.store.get('gps_broadcast','off')=='on'
        sats=u.gps.parser.satellites
        text(236,38,('Share on' if sharing else 'Local only'),ACCENT if sharing else MUTED,8,width=80)
        if centre:
            plotted=[]
            for p in sorted(dots,key=lambda p:-p['distance']):
                outside=p['distance']>scale;radius=min(p['distance']/scale,1.04)*r;rad=math.radians(p['bearing']);x=round(cx+math.sin(rad)*radius);y=round(cy-math.cos(rad)*radius)
                kind=p['node'].get('adv_type');color=MUTED if outside or p['stale'] else {1:'#75c8fa',2:'#ffbd72',3:'#c6a0f6'}.get(kind,ACCENT)
                if outside:d.ellipse((x-1,y-1,x+1,y+1),fill=color)
                elif p['stale']:d.ellipse((x-2,y-2,x+2,y+2),outline=color)
                elif kind==2:d.polygon(((x,y-3),(x-3,y+2),(x+3,y+2)),fill=color)
                elif kind==3:d.polygon(((x,y-3),(x-3,y),(x,y+3),(x+3,y)),fill=color)
                else:d.ellipse((x-2,y-2,x+2,y+2),fill=color)
                if p is chosen:d.ellipse((x-5,y-5,x+5,y+5),outline=TEXT)
                plotted.append((p,x,y,color,outside))
            boxes=[(3,22,88,48),(233,22,319,50),(cx-6,cy-6,cx+6,cy+6)]
            labels=sorted(plotted,key=lambda item:(item[0] is not chosen,item[0]['distance']))
            for p,x,y,color,outside in labels[:8]:
                if outside and p is not chosen:continue
                name=p['node'].get('name') or p['node']['public_key'][:6];width=min(78,math.ceil(u.text.width(name,9,p is chosen)))
                for lx,ly in ((x+6,y-7),(x-width-6,y-7),(x+6,y+5),(x-width-6,y+5),(x-width/2,y-18),(x-width/2,y+10)):
                    lx=max(4,min(315-width,lx));ly=max(24,min(140,ly));box=(lx-1,ly-1,lx+width+1,ly+11)
                    if any(box[0]<b[2] and box[2]>b[0] and box[1]<b[3] and box[3]>b[1] for b in boxes):continue
                    d.rectangle(box,fill=BG);text(lx,ly,name,color,9,p is chosen,width=width);boxes.append(box);break
            d.polygon(((cx,cy-4),(cx-3,cy+3),(cx+3,cy+3)),fill=ACCENT,outline=TEXT)
            count=sum(p['distance']<=scale for p in dots);text(7,139,f'{count}/{len(dots)} in range',MUTED,8,width=95)
            if not dots:text(7,124,'No other positions yet',MUTED,9,width=110)
        else:
            text(102,76,'No position yet',MUTED,11,width=125)
            text(102,94,'GPS or M for manual',MUTED,9,width=125)
        text(6,157,'↑↓ zoom  0 auto  ←→ node  Enter info  M pos',MUTED,9)
        u.draw_notice(img);return img
