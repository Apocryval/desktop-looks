#!/usr/bin/python3
"""Approved Desktop Looks asset migration. Defaults to a non-mutating staged review."""
import argparse,contextlib,datetime,fcntl,hashlib,importlib.util,json,os,re,shutil,subprocess,sys,tempfile,uuid,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'desktop-looks@local'))
import looks
WALLS=['wallpaperswide.com-microsoft-windows-95-wallpaper-1920x1080.jpg','wallpaperswide.com-microsoft-windows-95-wallpaper-2560x1080.jpg']
ICON_OLD='Pictures/App Icons/';ICON_NEW='.local/share/icons/custom-apps/windows95/'
FONT_DIRS=['Complete_friends_theme_pack_v1.0b_(high_color)_Fonts','vga_font','bitmap']
IMAGE={'.png','.jpg','.jpeg','.svg','.ico','.webp','.gif','.bmp'}
class Desktop:
 def wallpaper(self):return looks.run(['/usr/bin/gsettings','get','org.cinnamon.desktop.background','picture-uri'])
 def set_wallpaper(self,value):
  looks.run(['/usr/bin/gsettings','set','org.cinnamon.desktop.background','picture-uri',value])
  if self.wallpaper()!=value:raise RuntimeError('The desktop did not accept its new wallpaper reference')
 def sounds(self):return looks.run(['/usr/bin/gsettings','list-recursively','org.cinnamon.sounds'])
 def refresh_fonts(self,home):
  subprocess.run(['/usr/bin/fc-cache','-f',str(home/'.local/share/fonts')],check=True,capture_output=True,text=True,timeout=60)

def remap_relative(rel):
 if rel.startswith('.fonts/'):
  if Path(rel).name=='.uuid':return None
  return '.local/share/fonts/'+rel[len('.fonts/'):]
 if rel.startswith(ICON_OLD) and Path(rel).suffix.lower() in IMAGE:return ICON_NEW+rel[len(ICON_OLD):]
 if rel.startswith('Downloads/') and Path(rel).name in WALLS:return 'Pictures/Wallpapers/Windows95/'+Path(rel).name
 return rel

def remap_text(text,home):
 home=str(home)
 text=text.replace(home+'/.fonts/',home+'/.local/share/fonts/')
 text=text.replace(home+'/'+ICON_OLD,home+'/'+ICON_NEW)
 for name in WALLS:text=text.replace(home+'/Downloads/'+name,home+'/Pictures/Wallpapers/Windows95/'+name)
 text=text.replace(home+'/Pictures/App%20Icons/',home+'/'+ICON_NEW)
 return text

def nested(value,home):
 if isinstance(value,str):return remap_text(value,home)
 if isinstance(value,list):return [nested(v,home) for v in value]
 if isinstance(value,dict):return {k:nested(v,home) for k,v in value.items()}
 return value

def transform(source,target,home):
 home=Path(home);target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(source) as z:
  old=json.loads(z.read('manifest.json'));m=nested(old,home);files=[];seen=set()
  with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=5) as out:
   for item in old['files']:
    newrel=remap_relative(item['path'])
    if newrel is None:continue
    if newrel in seen:raise ValueError('Duplicate migrated asset: '+newrel)
    seen.add(newrel);entry=nested(item,home);entry['path']=newrel
    if newrel.startswith(ICON_NEW):entry['group']='icons'
    files.append(entry)
    if item['kind']=='file':
     content=z.read('payload/'+item['path'])
     if Path(newrel).suffix.lower() in looks.TEXT_SUFFIXES or Path(newrel).name in ['.gtkrc-2.0','index.theme','desktop-metadata']:
      try:content=remap_text(content.decode(),home).encode()
      except UnicodeDecodeError:pass
     out.writestr('payload/'+newrel,content)
   m['files']=files;m.setdefault('summary',{})['files']=len(files)
   m['asset_migration']={'version':1,'wallpapers':'Pictures/Wallpapers/Windows95','app_icons':ICON_NEW.rstrip('/'),'fonts':'.local/share/fonts'}
   out.writestr('manifest.json',json.dumps(m,indent=2,ensure_ascii=False))
 target.chmod(0o600)
 manager=looks.Looks(home,target.parent/'.validation',metadata=False);manager.inspect(target)
 with zipfile.ZipFile(target) as z:
  if z.testzip():raise RuntimeError('Migrated profile failed its archive integrity check')
 return m

def writable_parent(path):
 p=Path(path)
 while not p.exists():p=p.parent
 return os.access(p,os.W_OK)

def backup(home,dest,desktop):
 paths=[home/'Pictures/App Icons',home/'.fonts',home/'.local/share/fonts',home/'.local/share/applications',home/'.local/share/cinnamon/applets/desktop-looks@local',home/'.local/share/desktop-looks',home/'.config/nemo/desktop-metadata']
 paths += [home/'Downloads'/name for name in WALLS]
 files={}
 for path in paths:
  for p in ([path] if path.is_file() else path.rglob('*') if path.is_dir() else []):
   if p.is_file() and not p.is_symlink():files[str(p.relative_to(home))]=p
 manifest={'home':str(home),'wallpaper':desktop.wallpaper(),'sounds':desktop.sounds(),'sha256':{}}
 with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=5) as z:
  for rel,p in sorted(files.items()):
   manifest['sha256'][rel]=hashlib.sha256(p.read_bytes()).hexdigest();z.write(p,'home/'+rel,compress_type=zipfile.ZIP_STORED if p.suffix=='.look' else zipfile.ZIP_DEFLATED)
  z.writestr('backup-manifest.json',json.dumps(manifest,indent=2))
 Path(dest).chmod(0o600);return manifest

def copy_atomic(src,dest):
 dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(dir=dest.parent)
 try:
  with os.fdopen(fd,'wb') as f:f.write(Path(src).read_bytes())
  os.chmod(tmp,Path(src).stat().st_mode & 0o777);os.replace(tmp,dest)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)

def stage(home,where,settings=None):
 home=Path(home);where=Path(where);where.mkdir(parents=True,exist_ok=True)
 originals=sorted((home/'.local/share/desktop-looks').glob('*.look'))
 results=[]
 for source in originals:
  target=where/'profiles'/source.name;manifest=transform(source,target,home)
  results.append({'source':str(source),'staged':str(target),'name':manifest['name']})
 manager=looks.Looks(home,where/'capture-state',settings=settings)
 current,_=manager.capture('95 — Firefox and desktop layout',output=where/'current-before.look')
 current_target=where/'Current-95-Firefox.look';m=transform(current,current_target,home)
 plan={'home':str(home),'existing_profiles':results,'new_current_profile':str(current_target),'new_current_summary':m['summary'],'warnings':m.get('warnings',[]),'apply_completed':False}
 (where/'plan.json').write_text(json.dumps(plan,indent=2,ensure_ascii=False));return plan

def apply(home,where,settings=None,desktop=None):
 home=Path(home);where=Path(where);desktop=desktop or Desktop()
 required=[home/'Downloads',home/'Pictures',home/'.fonts',home/'.local/share/fonts',home/'.local/share/icons',home/'.local/share/applications',home/'.local/share/cinnamon/applets/desktop-looks@local',home/'.local/share/desktop-looks']
 denied=[str(p) for p in required if not writable_parent(p)]
 if denied:raise RuntimeError('Live folders are read-only in this session: '+', '.join(denied)+'. The staged update is safe to run from your normal desktop or a fresh authorized session.')
 plan=stage(home,where,settings);stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S');archive=where.parent/f'Desktop-Looks-backup-{stamp}.zip';before=backup(home,archive,desktop)
 moves=[]
 for name in WALLS:
  src=home/'Downloads'/name;dst=home/'Pictures/Wallpapers/Windows95'/name
  if src.exists():moves.append((src,dst))
 for src in (home/'Pictures/App Icons').glob('*'):
  if src.is_file() and src.suffix.lower() in IMAGE:moves.append((src,home/ICON_NEW/src.name))
 for name in FONT_DIRS:
  src=home/'.fonts'/name;dst=home/'.local/share/fonts'/name
  if src.exists():moves.append((src,dst))
 for src,dst in moves:
  if dst.exists():raise RuntimeError('Destination already exists; no files moved: '+str(dst))
 journal=[];created=[]
 store=home/'.local/share/desktop-looks';store.mkdir(parents=True,exist_ok=True)
 with (store/'.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  try:
   for src,dst in moves:dst.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(src),str(dst));journal.append((src,dst))
   for p in (home/'.local/share/applications').glob('*.desktop'):
    current=p.read_text(errors='replace');updated=remap_text(current,home)
    if updated!=current:p.write_text(updated)
   for item in plan['existing_profiles']:copy_atomic(item['staged'],item['source'])
   current_dest=store/f'current-firefox-layout-{uuid.uuid4().hex[:8]}.look';copy_atomic(plan['new_current_profile'],current_dest);created.append(current_dest)
   target=home/'.local/share/cinnamon/applets/desktop-looks@local';target.mkdir(parents=True,exist_ok=True)
   for p in (ROOT/'desktop-looks@local').iterdir():
    if p.is_file() and p.suffix in ['.py','.js','.json']:
     dest=target/p.name
     if not dest.exists():created.append(dest)
     copy_atomic(p,dest)
   previous_uri=before['wallpaper'];new_uri=remap_text(previous_uri,home)
   if new_uri!=previous_uri:desktop.set_wallpaper(new_uri)
   desktop.refresh_fonts(home)
   # Compare all moved file content against the source backup.
   for src,dst in journal:
    source_rel=str(src.relative_to(home))
    if dst.is_file():assert hashlib.sha256(dst.read_bytes()).hexdigest()==before['sha256'][source_rel]
    else:
     for rel,digest in before['sha256'].items():
      if rel.startswith(source_rel+'/') and Path(rel).name!='.uuid':assert hashlib.sha256((home/remap_relative(rel)).read_bytes()).hexdigest()==digest
   assert desktop.sounds()==before['sounds'],'Sound settings changed unexpectedly'
   helper=looks.Looks(home,where/'validation-state',settings=settings,metadata=False)
   for item in plan['existing_profiles']:helper.inspect(item['source'])
   helper.inspect(current_dest)
   live_text='\n'.join(p.read_text(errors='replace') for p in (home/'.local/share/applications').glob('*.desktop'))
   assert str(home)+'/Pictures/App Icons/' not in live_text,'An old icon reference remains'
   for p in [home/'.fonts/.uuid']:
    if p.exists():p.unlink()
   try:(home/'.fonts').rmdir()
   except OSError:pass
   (store/'active.json').write_text(json.dumps({'name':'95 — Firefox and desktop layout','profile':str(current_dest),'migration_backup':str(archive)}))
   plan.update({'apply_completed':True,'backup':str(archive),'moved_items':len(journal),'installed_version':'1.1.0','new_profile':str(current_dest),'wallpaper':desktop.wallpaper()})
  except Exception:
   for src,dst in reversed(journal):
    if dst.exists():src.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(dst),str(src))
   with zipfile.ZipFile(archive) as z:
    for name in z.namelist():
     if name.startswith('home/'):
      p=home/name[5:];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(name))
   for p in created:
    if p.is_file():p.unlink()
   try:desktop.set_wallpaper(before['wallpaper'])
   except Exception:pass
   raise
 (where/'plan.json').write_text(json.dumps(plan,indent=2,ensure_ascii=False));return plan

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--apply',action='store_true');p.add_argument('--home',default=str(Path.home()));p.add_argument('--stage',default=str(ROOT/'Migration-stage'));a=p.parse_args()
 try:
  result=apply(a.home,a.stage) if a.apply else stage(a.home,a.stage)
  print(json.dumps(result,indent=2,ensure_ascii=False));return 0
 except Exception as e:print(str(e),file=sys.stderr);return 1
if __name__=='__main__':sys.exit(main())
