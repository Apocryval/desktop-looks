"""Firefox appearance only. Theme activation is delegated to Firefox's AddonManager."""
import configparser,json,os,re,shutil,socket,struct,subprocess,tempfile,time,zipfile
from pathlib import Path,PurePosixPath
ROOTS=['.mozilla/firefox','.config/mozilla/firefox','.var/app/org.mozilla.firefox/.mozilla/firefox']
PREFS={'toolkit.legacyUserProfileCustomizations.stylesheets','browser.theme.toolbar-theme','browser.theme.content-theme','browser.uidensity','browser.tabs.inTitlebar','browser.uiCustomization.state','browser.toolbars.bookmarks.visibility','browser.tabs.vertical','ui.systemUsesDarkTheme','layout.css.prefers-color-scheme.content-override'}
PREFIXES=('font.name.','font.size.','browser.display.')
ASSETS={'.css','.svg','.png','.jpg','.jpeg','.gif','.webp','.ico','.ttf','.otf','.woff','.woff2'}
PAT=re.compile(r'^\s*user_pref\(("(?:[^"\\]|\\.)*")\s*,\s*(.*?)\);\s*$')
def appearance(key):return key in PREFS or key.startswith(PREFIXES)
def parse(text):
 result={}
 for line in text.splitlines():
  m=PAT.match(line)
  if m:
   try:result[json.loads(m[1])]=json.loads(m[2])
   except (ValueError,TypeError):pass
 return result

def patch(text,values,remove):
 lines=[]
 for line in text.splitlines():
  m=PAT.match(line)
  if m:
   try:
    if json.loads(m[1]) in remove:continue
   except ValueError:pass
  lines.append(line)
 for key,value in sorted(values.items()):lines.append('user_pref('+json.dumps(key)+', '+json.dumps(value,ensure_ascii=False)+');')
 return '\n'.join(lines)+'\n'

def profile(home):
 home=Path(home)
 for root in ROOTS:
  base=home/root;ini=base/'profiles.ini'
  if not ini.exists():continue
  config=configparser.ConfigParser(interpolation=None);config.read(ini)
  candidates=[]
  for section in config.sections():
   if section.startswith('Install') and config.has_option(section,'Default'):candidates.append(base/config[section]['Default'])
  candidates += [base/config[s]['Path'] if config[s].get('IsRelative','1')=='1' else Path(config[s]['Path']) for s in config.sections() if s.startswith('Profile') and config[s].get('Default')=='1']
  candidates += [base/config[s]['Path'] if config[s].get('IsRelative','1')=='1' else Path(config[s]['Path']) for s in config.sections() if s.startswith('Profile')]
  for p in candidates:
   if p.is_dir() and p.resolve().is_relative_to(home.resolve()):return p
 return None

def prefs_at(p):
 result={}
 for name in ['prefs.js','user.js']:
  f=p/name
  if f.exists():result.update(parse(f.read_text(errors='replace')))
 return result

def capture(home):
 p=profile(home)
 if p is None:return {'available':False},{}
 prefs=prefs_at(p);theme_id=prefs.get('extensions.activeThemeID','default-theme@mozilla.org');theme_name=theme_id;theme_path=None
 db=p/'extensions.json'
 if db.exists():
  for addon in json.loads(db.read_text()).get('addons',[]):
   if addon.get('type')=='theme' and (addon.get('id')==theme_id):
    theme_name=addon.get('defaultLocale',{}).get('name',theme_id)
    if addon.get('path'):
     q=Path(addon['path'])
     if q.is_file() and q.resolve().is_relative_to(p.resolve()):theme_path=q
 sources={}
 chrome=p/'chrome'
 if chrome.is_dir():
  for q in chrome.rglob('*'):
   if q.is_file() and not q.is_symlink() and q.suffix.lower() in ASSETS:sources['@firefox/chrome/'+str(q.relative_to(chrome))]=q
 if theme_path:sources['@firefox/theme.xpi']=theme_path
 return {'available':True,'profile':str(p.relative_to(home)),'preferences':{k:v for k,v in prefs.items() if appearance(k)},'theme_id':theme_id,'theme_name':theme_name,'chrome_present':chrome.is_dir()},sources

def allowed(rel):
 p=PurePosixPath(rel)
 return not p.is_absolute() and '..' not in p.parts and (rel=='@firefox/theme.xpi' or rel.startswith('@firefox/chrome/') and p.suffix.lower() in ASSETS)

def validate(data,z,items):
 if not data:return
 if any(not appearance(k) for k in data.get('preferences',{})):raise ValueError('Non-appearance Firefox preference in profile')
 for value in data.get('preferences',{}).values():
  if not isinstance(value,(str,bool,int,float)):raise ValueError('Unsupported Firefox preference value')
 theme_id=data.get('theme_id','')
 if not isinstance(theme_id,str) or len(theme_id)>256:raise ValueError('Invalid Firefox theme identifier')
 for item in items:
  if item.get('group')!='firefox':continue
  if not allowed(item['path']) or item['kind']!='file':raise ValueError('Invalid Firefox asset')
  if item['path']=='@firefox/theme.xpi':
   import io
   with zipfile.ZipFile(io.BytesIO(z.read('payload/'+item['path']))) as package:
    manifest=json.loads(package.read('manifest.json'))
    ident=manifest.get('browser_specific_settings',manifest.get('applications',{})).get('gecko',{}).get('id')
    if not ('theme' in manifest or 'dark_theme' in manifest) or any(k in manifest for k in ['background','content_scripts','experiment_apis']):raise ValueError('Firefox asset is not a static theme')
    if ident and ident!=theme_id:raise ValueError('Firefox theme ID differs from its package')

class Marionette:
 def __init__(self,connection):self.sock=connection;self.ident=0;self.read()
 def exact(self,count):
  data=b''
  while len(data)<count:
   part=self.sock.recv(count-len(data))
   if not part:raise RuntimeError('Firefox closed its automation connection')
   data+=part
  return data
 def read(self):
  size=b''
  while True:
   c=self.exact(1)
   if c==b':':break
   if not c.isdigit() or len(size)>9:raise RuntimeError('Invalid Firefox response')
   size+=c
  return json.loads(self.exact(int(size)))
 def call(self,command,params=None):
  self.ident+=1;body=json.dumps([0,self.ident,command,params or {}]).encode();self.sock.sendall(str(len(body)).encode()+b':'+body)
  while True:
   frame=self.read()
   if isinstance(frame,list) and len(frame)==4 and frame[0]==1 and frame[1]==self.ident:
    if frame[2]:raise RuntimeError('Firefox: '+str(frame[2].get('message',frame[2])))
    return frame[3]

TRANSIENT={'marionette.port':0,'browser.startup.page':0,'browser.sessionstore.resume_session_once':False,'browser.sessionstore.resume_from_crash':False,'browser.startup.homepage_override.mstone':'ignore','browser.tabs.warnOnClose':False}
THEME_SCRIPT='''const done=arguments[arguments.length-1]; const wanted=arguments[0]; const xpi=arguments[1];
(async()=>{const {AddonManager}=ChromeUtils.importESModule("resource://gre/modules/AddonManager.sys.mjs");
let addon=await AddonManager.getAddonByID(wanted);
if(!addon && xpi){const file=Components.classes["@mozilla.org/file/local;1"].createInstance(Components.interfaces.nsIFile);file.initWithPath(xpi);const install=await AddonManager.getInstallForFile(file);if(install.addon.id!==wanted || install.addon.type!=="theme")throw new Error("Theme package does not match this look");await install.install();addon=await AddonManager.getAddonByID(wanted);}
if(!addon || addon.type!=="theme")throw new Error("Install the saved theme in Firefox first");await addon.enable();done({ok:true,id:addon.id});})().catch(error=>done({ok:false,error:String(error)}));'''

def activate_theme(p,theme_id,xpi=None):
 # No add-on database edits. Firefox performs installation/activation itself in an offline session.
 if prefs_at(p).get('extensions.activeThemeID','default-theme@mozilla.org')==theme_id:return
 binary=shutil.which('firefox')
 if not binary:raise RuntimeError('Firefox is not installed')
 before_user=(p/'user.js').read_bytes() if (p/'user.js').exists() else None
 before_prefs=(p/'prefs.js').read_text() if (p/'prefs.js').exists() else ''
 original_values=parse(before_prefs);client=None;proc=None;session_names=['sessionstore.jsonlz4','sessionCheckpoints.json','sessionstore-backups']
 with tempfile.TemporaryDirectory(prefix='desktop-looks-firefox-') as scratch:
  scratch=Path(scratch)
  for name in session_names:
   src=p/name
   if src.is_dir():shutil.copytree(src,scratch/name)
   elif src.is_file():shutil.copy2(src,scratch/name)
  with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
  temporary={**TRANSIENT,'marionette.port':port}
  (p/'user.js').write_text(patch(before_user.decode() if before_user else '',temporary,set(temporary)))
  try:
   proc=subprocess.Popen([binary,'--headless','--no-remote','--offline','--marionette','--remote-allow-system-access','--profile',str(p),'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   deadline=time.monotonic()+40
   while time.monotonic()<deadline:
    if proc.poll() is not None:raise RuntimeError('Firefox could not start its offline theme session')
    try:conn=socket.create_connection(('127.0.0.1',port),timeout=1);conn.settimeout(25);client=Marionette(conn);break
    except (OSError,RuntimeError):time.sleep(.2)
   if client is None:raise RuntimeError('Firefox theme session timed out')
   client.call('WebDriver:NewSession',{'capabilities':{'alwaysMatch':{}}})
   client.call('Marionette:SetContext',{'value':'chrome'})
   client.call('WebDriver:SetTimeouts',{'script':20000})
   result=client.call('WebDriver:ExecuteAsyncScript',{'script':THEME_SCRIPT,'args':[theme_id,str(xpi) if xpi else None],'newSandbox':True,'sandbox':None})
   if isinstance(result,dict) and 'value' in result:result=result['value']
   if not result.get('ok'):raise RuntimeError(result.get('error','Firefox theme activation failed'))
  finally:
   if client:
    try:client.call('Marionette:Quit',{'flags':['eAttemptQuit']})
    except Exception:pass
    client.sock.close()
   if proc and proc.poll() is None:
    try:proc.wait(timeout=12)
    except subprocess.TimeoutExpired:
     proc.terminate()
     try:proc.wait(timeout=8)
     except subprocess.TimeoutExpired:proc.kill();proc.wait()
   if before_user is None:(p/'user.js').unlink(missing_ok=True)
   else:(p/'user.js').write_bytes(before_user)
   current=(p/'prefs.js').read_text() if (p/'prefs.js').exists() else before_prefs
   (p/'prefs.js').write_text(patch(current,{k:original_values[k] for k in temporary if k in original_values},set(temporary)))
   for name in session_names:
    dest=p/name;saved=scratch/name
    if dest.is_dir():shutil.rmtree(dest)
    elif dest.exists():dest.unlink()
    if saved.is_dir():shutil.copytree(saved,dest)
    elif saved.exists():shutil.copy2(saved,dest)


def restore(home,z,data,items,write,remap):
 if not data or not data.get('available'):return []
 p=profile(home)
 if p is None:return ['Start Firefox once to create a profile, then apply its saved appearance.']
 theme_xpi=None
 with tempfile.TemporaryDirectory(prefix='desktop-looks-theme-') as scratch:
  saved_chrome=set()
  for item in items:
   if item['group']!='firefox':continue
   rel=item['path'];content=z.read('payload/'+rel)
   if rel=='@firefox/theme.xpi':theme_xpi=Path(scratch)/'theme.xpi';theme_xpi.write_bytes(content);continue
   sub=rel.removeprefix('@firefox/chrome/');target=p/'chrome'/sub
   if not target.parent.resolve().is_relative_to(p.resolve()):raise ValueError('Firefox CSS path escapes the profile')
   if target.suffix.lower() in ['.css','.svg']:
    try:content=remap(content.decode()).encode()
    except UnicodeDecodeError:pass
   write(target,content);saved_chrome.add(sub)
  for name in ['userChrome.css','userContent.css']:
   if name not in saved_chrome:(p/'chrome'/name).unlink(missing_ok=True)
  values={k:remap(v) if isinstance(v,str) else v for k,v in data.get('preferences',{}).items()}
  for name in ['prefs.js','user.js']:
   path=p/name
   if name=='user.js' and not path.exists():continue
   current=path.read_text() if path.exists() else ''
   remove={k for k in parse(current) if appearance(k)}|set(PREFS)
   write(path,patch(current,values,remove).encode())
  activate_theme(p,data['theme_id'],theme_xpi)
 return []
