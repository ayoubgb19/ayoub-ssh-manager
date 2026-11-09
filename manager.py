#!/usr/bin/env python3
"""Ayoub SSH/Xray terminal manager (Ubuntu 24.04 prototype)."""
import os, sys, json, subprocess, datetime, uuid, secrets, base64, re, getpass, pathlib, tempfile
ROOT=pathlib.Path('/etc/ayoub-new-manager')
DB=ROOT/'accounts.json'; CFG=ROOT/'settings.json'
XR=pathlib.Path('/usr/local/etc/xray/config.json')
BLUE='\033[94m'; RED='\033[91m'; GREEN='\033[92m'; RESET='\033[0m'
def run(*a,**kw): return subprocess.run(a,text=True,**kw)
def load(path,default): return json.loads(path.read_text()) if path.exists() else default
def save(path,obj):
 path.parent.mkdir(parents=True,exist_ok=True)
 fd,tmp=tempfile.mkstemp(dir=path.parent)
 try:
  with os.fdopen(fd,'w') as f: json.dump(obj,f,indent=2)
  os.chmod(tmp,0o600); os.replace(tmp,path)
 finally:
  if os.path.exists(tmp): os.unlink(tmp)
def db(): return load(DB,{k:{} for k in ('ssh','vmess','vless','trojan')})
def settings(): return load(CFG,{'domain':'localhost'})
def active(n): return run('systemctl','is-active','--quiet',n).returncode==0
def title(t):
 print(BLUE+'╔'+'═'*48+'╗'+RESET)
 print(RED+'║'+t.center(48)+'║'+RESET)
 print(BLUE+'╚'+'═'*48+'╝'+RESET)
def prompt(t): return input(GREEN+t+': '+RESET).strip()
def pause(): input('\nPress Enter to return...')
def days(s): return (datetime.date.fromisoformat(s)-datetime.date.today()).days
def expiry(n): return (datetime.date.today()+datetime.timedelta(days=n)).isoformat()
def number(t,default):
 s=prompt('%s [%s]'%(t,default)); n=int(s or default)
 if n<1: raise ValueError('Must be positive')
 return n
def username():
 n=prompt('User')
 if not re.fullmatch(r'[a-z][a-z0-9_-]{0,25}',n): raise ValueError('Use lowercase letters, digits, - or _')
 return n
def xray_config(d):
 ins=[]
 for typ,port in (('vmess',10001),('vless',10002),('trojan',10003)):
  clients=[]
  for name,a in d[typ].items():
   if days(a['expires'])<=0: continue
   c={'email':typ+'-'+name}
   if typ=='trojan': c['password']=a['secret']
   else: c['id']=a['secret']
   if typ=='vmess': c['alterId']=0
   clients.append(c)
  cfg={'clients':clients}
  if typ=='vless': cfg['decryption']='none'
  ins.append({'tag':typ,'listen':'127.0.0.1','port':port,'protocol':typ,'settings':cfg,
              'streamSettings':{'network':'ws','wsSettings':{'path':'/'+typ}}})
 return {'log':{'loglevel':'warning'},'inbounds':ins,'outbounds':[{'protocol':'freedom'}]}
def apply(d):
 XR.parent.mkdir(parents=True,exist_ok=True)
 fd,tmp=tempfile.mkstemp(suffix='.json',dir=XR.parent)
 with os.fdopen(fd,'w') as f: json.dump(xray_config(d),f,indent=2)
 try:
  r=run('/usr/local/bin/xray','run','-test','-config',tmp,capture_output=True)
  if r.returncode: raise RuntimeError('Xray validation failed: '+(r.stderr or r.stdout)[-1000:])
  old=XR.read_bytes() if XR.exists() else None
  os.replace(tmp,XR)
  r=run('systemctl','restart','xray')
  if r.returncode or not active('xray'):
   if old is not None: XR.write_bytes(old); run('systemctl','restart','xray')
   raise RuntimeError('Xray restart failed; previous config restored if it existed')
 finally:
  if os.path.exists(tmp): os.unlink(tmp)
def link(typ,name,a):
 host=settings()['domain']; secret=a['secret']
 if typ=='vmess':
  obj={'v':'2','ps':name,'add':host,'port':'443','id':secret,'aid':'0','scy':'auto',
       'net':'ws','type':'none','host':host,'path':'/vmess','tls':'tls','sni':host}
  return 'vmess://'+base64.b64encode(json.dumps(obj,separators=(',',':')).encode()).decode()
 return f'{typ}://{secret}@{host}:443?'+('encryption=none&' if typ=='vless' else '')+f'security=tls&sni={host}&type=ws&host={host}&path=%2F{typ}#{name}'
def details(typ,name,a):
 host=settings()['domain']
 if typ in ('vmess','vless','trojan'):
  os.system('clear')
  def sep(): print(BLUE+'◇'+'─'*43+'◇'+RESET)
  sep()
  print(GREEN+'Xray/'+typ.capitalize()+' Account'+RESET)
  sep()
  rows=[
   ('Remarks',name),
   ('Domain',host),
   ('User Quota',str(a.get('quota',0))+' GB (not enforced)'),
   ('User Ip',str(a.get('ip',0))+' IP (not enforced)'),
   ('Port TLS','443'),
   ('id' if typ!='trojan' else 'Password',a['secret']),
   ('Security','auto' if typ=='vmess' else 'tls'),
   ('Network','ws'),
   ('Path','/'+typ),
   ('ServiceName','Not configured (gRPC)'),
  ]
  for key,value in rows:
   print(GREEN+key.ljust(19)+' : '+str(value)+RESET)
  sep()
  print(GREEN+'Link TLS'+RESET)
  print(GREEN+link(typ,name,a)+RESET)
  sep()
  print(GREEN+'Link none TLS : Not configured'+RESET)
  sep()
  print(GREEN+'Link GRPC     : Not configured'+RESET)
  sep()
  print(GREEN+'Format OpenClash : Not configured'+RESET)
  sep()
  print(GREEN+'Aktif Selama   : '+str(max(0,days(a['expires'])))+' Hari'+RESET)
  print(GREEN+'Dibuat Pada    : '+a.get('created',datetime.date.today().isoformat())+RESET)
  print(GREEN+'Berakhir Pada  : '+a['expires']+RESET)
  sep()
  print(GREEN+'AYOUB SSH XRAY MANAGER'+RESET)
  input(GREEN+'\nPress any key to back on menu'+RESET)
 else:
  title('SSH ACCOUNT')
  print(GREEN+'Username      : '+name+'\nHost          : '+host+
        '\nPort OpenSSH  : 22\nPort SSH WS   : 443 (/ssh)'+
        '\nExpiry        : '+a['expires']+
        '\nIP limit      : '+str(a.get('ip',0))+' (not enforced)'+RESET)
  pause()

def create(typ,trial=False):
 name=username(); d=db()
 if name in d[typ]: raise ValueError('Account exists')
 ip=number('IP limit (not enforced)',2)
 length=1 if trial else number('Days',30)
 if typ=='ssh':
  if run('id',name,capture_output=True).returncode==0: raise ValueError('Linux user exists')
  password=getpass.getpass('Password (8+ characters): ')
  if len(password)<8: raise ValueError('Password too short')
  r=run('useradd','-m','-s','/bin/bash',name)
  if r.returncode: raise RuntimeError('useradd failed')
  try:
   if run('chpasswd',input=name+':'+password+'\n').returncode: raise RuntimeError('chpasswd failed')
   if run('chage','-E',expiry(length),name).returncode: raise RuntimeError('chage failed')
  except Exception:
   run('userdel','-r',name); raise
  a={'expires':expiry(length),'created':datetime.date.today().isoformat(),'ip':ip}; d[typ][name]=a; save(DB,d)
 else:
  quota=number('Quota GB (not enforced)',100)
  a={'expires':expiry(length),'created':datetime.date.today().isoformat(),'ip':ip,'quota':quota,
     'secret':secrets.token_urlsafe(24) if typ=='trojan' else str(uuid.uuid4())}
  d[typ][name]=a; apply(d); save(DB,d)
 details(typ,name,a)
def renew(typ):
 name=username(); d=db(); a=d[typ][name]; n=number('Add days',30)
 start=max(datetime.date.today(),datetime.date.fromisoformat(a['expires']))
 a['expires']=(start+datetime.timedelta(days=n)).isoformat()
 if typ=='ssh':
  if run('chage','-E',a['expires'],name).returncode: raise RuntimeError('chage failed')
 else: apply(d)
 save(DB,d); details(typ,name,a)
def delete(typ):
 name=username(); d=db()
 if name not in d[typ]: raise ValueError('Not found')
 if prompt('Confirm delete (yes)')!='yes': return
 if typ=='ssh':
  if run('userdel','-r',name).returncode: raise RuntimeError('userdel failed')
 else:
  del d[typ][name]; apply(d)
 if typ=='ssh': del d[typ][name]
 save(DB,d); print('Deleted'); pause()
def list_accounts(typ):
 title(typ.upper()+' USERS')
 for n,a in db()[typ].items():
  print(n.ljust(26),a['expires'],'ACTIVE' if days(a['expires'])>0 else 'EXPIRED')
 pause()
def manage(typ):
 while True:
  title(typ.upper()+' MENU')
  print('[1] Create Account\n[2] Trial Account\n[3] Delete Account\n[4] Renew Account\n[5] List Accounts\n[6] Account Details\n[0] Back To Menu')
  choice=prompt('Select menu')
  if choice=='0': return
  try:
   if choice in ('1','2'): create(typ,choice=='2')
   elif choice=='3': delete(typ)
   elif choice=='4': renew(typ)
   elif choice=='5': list_accounts(typ)
   elif choice=='6':
    n=username(); details(typ,n,db()[typ][n])
  except Exception as e:
   print(RED+'ERROR: '+str(e)+RESET); pause()
def dashboard():
 import platform, socket
 os.system('clear')
 d=db(); s=settings(); host=s.get('domain','localhost')
 try:
  up=int(float(pathlib.Path('/proc/uptime').read_text().split()[0]))
  uptime=f'{up//86400} days, {(up%86400)//3600} hours, {(up%3600)//60} minutes'
 except Exception: uptime='N/A'
 try:
  m={}
  for line in pathlib.Path('/proc/meminfo').read_text().splitlines():
   k,v=line.split(':',1);m[k]=int(v.strip().split()[0])//1024
  ram=f"{m.get('MemTotal',0)} / {m.get('MemTotal',0)-m.get('MemAvailable',0)} MB"
 except Exception: ram='N/A'
 try: cpu=f'{os.cpu_count()}'
 except Exception: cpu='N/A'
 try: load=f'{os.getloadavg()[0]:.2f}'
 except Exception: load='N/A'
 try:
  ip=run('hostname','-I',capture_output=True).stdout.split()[0]
 except Exception: ip='N/A'
 def line(txt,width=59):print(BLUE+'│ '+txt.ljust(width-3)+'│'+RESET)
 def frame(title_text):
  print(BLUE+'╭'+'─'*57+'╮'+RESET)
  print(BLUE+'│ '+RED+title_text.center(55)+BLUE+' │'+RESET)
  print(BLUE+'╰'+'─'*57+'╯'+RESET)
 def pair(label,value):
  print(BLUE+'│ '+RED+'● '+BLUE+label.ljust(15)+GREEN+' = '+RESET+str(value))
 print(GREEN+' ✧✧  AYOUB SSH XRAY MANAGER  ✧✧'+RESET)
 print()
 frame('Welcome To Ayoub SSH Xray Manager')
 print(BLUE+'╭'+'─'*57+'╮'+RESET)
 pair('SYSTEM OS',platform.platform())
 pair('SYSTEM CORE',cpu)
 pair('SERVER RAM',ram)
 pair('LOADCPU',load)
 pair('DATE',datetime.datetime.now().strftime('%d-%m-%Y'))
 pair('TIME',datetime.datetime.now().strftime('%H:%M:%S'))
 pair('UPTIME',uptime)
 pair('IP VPS',ip)
 pair('DOMAIN',host)
 print(BLUE+'╰'+'─'*57+'╯'+RESET)
 print('                 >>> INFORMATION ACCOUNT <<<')
 print(BLUE+'          '+'─'*42+RESET)
 for label,key in (('SSH/OPENVPN/UDP','ssh'),('VMESS/WS/GRPC','vmess'),('VLESS/WS/GRPC','vless'),('TROJAN/WS/GRPC','trojan')):
  print(GREEN+'          '+label.ljust(20)+' = '+str(len(d[key]))+RESET)
 print(BLUE+'          '+'─'*42+RESET)
 print('                 >>> SERVICE STATUS <<<')
 print(BLUE+'╭'+'─'*57+'╮'+RESET)
 for items in (('SSH','ssh','XRAY','xray'),('SSH-WS','ssh-websocket','CADDY','caddy')):
  left=GREEN+'ON'+RESET if active(items[1]) else RED+'OFF'+RESET
  right=GREEN+'ON'+RESET if active(items[3]) else RED+'OFF'+RESET
  print(BLUE+'│ '+RESET+items[0].ljust(13)+left+'     '+items[2].ljust(13)+right)
 print(BLUE+'╰'+'─'*57+'╯'+RESET)
 print(BLUE+'╭'+'─'*57+'╮'+RESET)
 entries=[
 ('[01] SSH MENU','[08] BACKUP / RESTORE','[15] MENU BOT'),
 ('[02] VMESS MENU','[09] CPU / RAM','[16] CHANGE DOMAIN'),
 ('[03] VLESS MENU','[10] RESTART ALL','[17] FIX SSL'),
 ('[04] TROJAN MENU','[11] TELE BOT','[18] CHANGE BANNER'),
 ('[05] SERVICE STATUS','[12] UPDATE MENU','[19] RESTART BANNER'),
 ('[06] EXTRA TOOLS','[13] RUNNING','[20] SPEEDTEST'),
 ('[07] INSTALL UDP','[14] INFO PORT','[21] EXTRA MENU')]
 for row in entries:
  print(BLUE+'│ '+RESET+' │ '.join(x.ljust(19) for x in row)+BLUE+'│'+RESET)
 print(BLUE+'╰'+'─'*57+'╯'+RESET)
 print(BLUE+'╭'+'─'*57+'╮'+RESET)
 line('Script Version  =  AYOUB MANAGER 2026')
 print(BLUE+'╰'+'─'*57+'╯'+RESET)
 print()
 print('Note: menus 06-21 are visual placeholders; only 01-05 work.')

def main():
 if os.geteuid()!=0: sys.exit('Run: sudo menu')
 while True:
  dashboard(); c=prompt('Options')
  if c in ('0','00'): return
  if c in ('1','01','2','02','3','03','4','04'):
   manage({'1':'ssh','2':'vmess','3':'vless','4':'trojan'}[str(int(c))])
  elif c in ('5','05'):
   for s in ('ssh','ssh-websocket','xray','caddy'): print(s,'ON' if active(s) else 'OFF')
   pause()
if __name__=='__main__': main()
