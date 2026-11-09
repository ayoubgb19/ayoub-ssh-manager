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
 title('Xray/'+typ.upper()+' Account' if typ!='ssh' else 'SSH ACCOUNT')
 print(GREEN+'Remarks       : '+name+'\nDomain        : '+settings()['domain']+
       '\nExpiry        : '+a['expires']+'\nDays left     : '+str(max(0,days(a['expires'])))+RESET)
 print('IP limit      :',a.get('ip',0),'(not enforced)')
 if typ!='ssh':
  print('Quota         :',a.get('quota',0),'GB (not enforced)')
  print('Port TLS      : 443\nNetwork       : ws\nPath          : /'+typ+'\nLink TLS:')
  print(GREEN+link(typ,name,a)+RESET)
 else:
  print('SSH port      : 22\nSSH WS        : wss://'+settings()['domain']+'/ssh')
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
  a={'expires':expiry(length),'ip':ip}; d[typ][name]=a; save(DB,d)
 else:
  quota=number('Quota GB (not enforced)',100)
  a={'expires':expiry(length),'ip':ip,'quota':quota,
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
 title('Welcome To SSH XRAY Manager')
 print('SYSTEM OS   :',run('uname','-s',capture_output=True).stdout.strip())
 print('DATE        :',datetime.datetime.now().strftime('%d-%m-%Y %H:%M:%S'))
 print('DOMAIN      :',settings()['domain'])
 try:
  mem=pathlib.Path('/proc/meminfo').read_text().splitlines()
  print('RAM         :',mem[0].split(':')[1].strip())
  print('UPTIME      :',pathlib.Path('/proc/uptime').read_text().split()[0],'seconds')
 except OSError: pass
 print(BLUE+'─'*48+RESET)
 for k,v in db().items(): print(k.upper().ljust(13),':',len(v))
 print(BLUE+'─'*48+RESET)
 for s in ('ssh','ssh-websocket','xray','caddy'):
  print(s.ljust(14),':',GREEN+'ON'+RESET if active(s) else RED+'OFF'+RESET)
 print(BLUE+'─'*48+RESET)
 print('[01] SSH MENU      [02] VMESS MENU\n[03] VLESS MENU    [04] TROJAN MENU\n[05] CHECK SERVICES\n[00] EXIT')
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
