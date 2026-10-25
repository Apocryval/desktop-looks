#!/usr/bin/python3
"""Desktop Looks: local Cinnamon appearance snapshots, not account backups."""
import argparse
import contextlib
import datetime as dt
import fcntl
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import zipfile
import firefox_looks as firefox

APPLET = 'desktop-looks@local'
GROUPS = {'desktop': 'Desktop, panels and desklets', 'icons': 'App and folder icons',
          'steam': 'Steam / Millennium', 'discord': 'Discord / Vencord', 'firefox': 'Firefox appearance'}
SCHEMAS = {
 'org.cinnamon.theme': None,
 'org.cinnamon.desktop.interface': ['gtk-theme','icon-theme','cursor-theme','cursor-size','font-name','document-font-name','monospace-font-name','text-scaling-factor','gtk-color-scheme'],
 'org.cinnamon.desktop.wm.preferences': ['theme','titlebar-font','titlebar-uses-system-font','button-layout'],
 'org.cinnamon.desktop.background': None,
 'org.cinnamon.desktop.background.slideshow': None,
 'org.cinnamon.settings-daemon.plugins.xsettings': ['antialiasing','hinting','rgba-order'],
 'org.nemo.desktop': ['font','home-icon-visible','computer-icon-visible','trash-icon-visible','volumes-visible','desktop-layout','use-desktop-grid'],
 'org.nemo.icon-view': ['default-zoom-level','captions'],
}
ROOT_KEYS = ['enabled-applets','enabled-desklets','enabled-extensions','favorite-apps',
             'next-applet-id','next-desklet-id','app-menu-icon-name','app-menu-label','lock-desklets']
ROOT_PREFIXES = ('panel-', 'panels-', 'desktop-effects', 'desklet-', 'window-effect-')
TREES = {
 'desktop': ['.themes','.icons','.fonts','.local/share/themes','.local/share/icons',
             '.local/share/fonts','.local/share/cinnamon/applets','.local/share/cinnamon/desklets',
             '.local/share/cinnamon/extensions','.local/share/cinnamon/themes','.config/cinnamon/spices',
             '.config/qt5ct','.config/qt6ct'],
 'icons': ['Pictures/App Icons','.local/share/icons/custom-apps'],
 'steam': ['.local/share/Steam/millennium/themes','.local/share/Steam/steamui/skins'],
 'discord': ['.config/Vencord/themes','.var/app/com.discordapp.Discord/config/Vencord/themes'],
}
FIXED = {
 'desktop': ['.gtkrc-2.0','.config/gtk-3.0/gtk.css','.config/gtk-3.0/settings.ini',
             '.config/gtk-4.0/gtk.css','.config/gtk-4.0/settings.ini','.config/nemo/desktop-metadata'],
 'steam': ['.config/millennium/quick.css'],
 'discord': ['.config/Vencord/settings/quickCss.css',
             '.var/app/com.discordapp.Discord/config/Vencord/settings/quickCss.css'],
}
VC_KEYS = ['enabledThemes','themeLinks','useQuickCss','frameless','transparent','windowsMaterial','nativeTitleBar','disableMinSize']
ASSET_SUFFIXES = {'.png','.jpg','.jpeg','.gif','.webp','.svg','.ico','.bmp','.avif','.ttf','.otf','.woff','.woff2','.css','.cur','.ani'}
TEXT_SUFFIXES = {'.css','.json','.ini','.conf','.theme','.desktop','.rc','.svg','.js'}


def run(argv, check=True):
    p = subprocess.run(argv, text=True, capture_output=True, timeout=30)
    if check and p.returncode:
        raise RuntimeError(f'{argv[0]}: {p.stderr.strip() or "operation failed"}')
    return p.stdout.strip()


class Settings:
    def capture(self):
        available = set(run(['gsettings','list-schemas']).splitlines())
        result = {}
        for schema, wanted in {**SCHEMAS, 'org.cinnamon': []}.items():
            if schema not in available:
                continue
            keys = run(['gsettings','list-keys',schema]).splitlines()
            if schema == 'org.cinnamon':
                wanted = [k for k in keys if k in ROOT_KEYS or k.startswith(ROOT_PREFIXES)]
            for key in keys if wanted is None else wanted:
                if key not in keys:
                    continue
                value = run(['gsettings','get',schema,key])
                if schema == 'org.cinnamon' and key == 'enabled-applets':
                    value = preserve_manager(value, '[]', capture=True)
                result.setdefault(schema,{})[key] = value
        return result

    def apply(self, values, remap):
        available = set(run(['gsettings','list-schemas']).splitlines())
        current_manager = run(['gsettings','get','org.cinnamon','enabled-applets']) if 'org.cinnamon' in available else '[]'
        warnings = []
        # Apply panel definitions first, then applets after their configuration files exist.
        for schema, keys in values.items():
            if schema not in available:
                warnings.append(f'Skipped missing settings schema: {schema}')
                continue
            valid = set(run(['gsettings','list-keys',schema]).splitlines())
            for key, value in sorted(keys.items(), key=lambda kv: kv[0]=='enabled-applets'):
                if key not in valid:
                    warnings.append(f'Skipped unavailable setting: {schema}/{key}')
                    continue
                if schema == 'org.cinnamon' and key == 'enabled-applets':
                    value = preserve_manager(value, current_manager, panels=keys.get('panels-enabled',''))
                run(['gsettings','set',schema,key,remap(value)])
        if 'org.cinnamon' in values and 'enabled-applets' in values['org.cinnamon']:
            entries=variants(run(['gsettings','get','org.cinnamon','enabled-applets']))
            ids=[int(v.split(':')[-1]) for v in entries if v.split(':')[-1].isdigit()]
            next_id=int(run(['gsettings','get','org.cinnamon','next-applet-id']))
            if ids and next_id<=max(ids):run(['gsettings','set','org.cinnamon','next-applet-id',str(max(ids)+1)])
        return warnings


def variants(value):
    # These Cinnamon list values contain only quoted strings; use GLib when available.
    try:
        from gi.repository import GLib
        return GLib.Variant.parse(None,value,None,None).unpack()
    except Exception:
        import ast
        try: return ast.literal_eval(value.removeprefix('@as '))
        except Exception: return []


def preserve_manager(value, current, capture=False, panels=''):
    saved = [v for v in variants(value) if APPLET not in v]
    if capture:
        return repr(saved)
    panel_ids = [s.split(':')[0] for s in variants(panels)]
    for v in variants(current):
        if APPLET in v:
            fields=v.split(':')
            if panel_ids and fields[0] not in panel_ids: fields[0]=panel_ids[0]
            # Avoid instance-id collisions with the target profile's applets.
            ids=[int(x.split(':')[-1]) for x in saved if x.split(':')[-1].isdigit()]
            if fields[-1].isdigit() and int(fields[-1]) in ids: fields[-1]=str(max(ids+[0])+1)
            saved.append(':'.join(fields))
    return repr(saved)


def read_json(path):
    if not path.exists(): return {}
    value=json.loads(path.read_text())
    if not isinstance(value,dict): raise ValueError(f'Expected a JSON object: {path.name}')
    return value


def icon_line(text):
    return desktop_entry_value(text,'Icon')


def desktop_entry_value(text,key):
    section=False
    for line in text.splitlines():
        if line.startswith('['): section=line.strip()=='[Desktop Entry]'
        if section and line.startswith(key+'='): return line[len(key)+1:]
    return None


def change_icon(text, icon):
    lines=text.splitlines(); section=False; done=False; result=[]
    for line in lines:
        if line.startswith('['):
            if section and not done and icon is not None: result.append('Icon='+icon); done=True
            section=line.strip()=='[Desktop Entry]'
        if section and re.match(r'^Icon(?:\[[^\]]+\])?=',line):
            if icon is not None: result.append(line.split('=',1)[0]+'='+icon)
            done=True
        else: result.append(line)
    if section and not done and icon is not None: result.append('Icon='+icon)
    return '\n'.join(result)+'\n'


def discord_theme_summary(manifest):
    if 'discord' not in manifest.get('groups',[]):return ''
    names=[];found=False
    for patch in manifest.get('json_patches',[]):
        if patch.get('group')!='discord':continue
        found=True
        values=patch.get('values',{})
        names.extend(values.get('enabledThemes',[]))
        links=values.get('themeLinks',[])
        if links:names.append(f'{len(links)} online theme(s)')
    if not found:return 'Discord theme: no saved Vencord settings'
    return 'Discord theme: '+(', '.join(dict.fromkeys(names)) if names else 'no theme selected')


def change_window_class(text,value):
    result=[];section=False;done=False
    for line in text.splitlines():
        if line.startswith('['):
            if section and not done:result.append('StartupWMClass='+value);done=True
            section=line.strip()=='[Desktop Entry]'
        if section and line.startswith('StartupWMClass='):
            if not done:result.append('StartupWMClass='+value);done=True
        else:result.append(line)
    if section and not done:result.append('StartupWMClass='+value)
    return '\n'.join(result)+'\n'


class Looks:
    def __init__(self, home=None, store=None, settings=None, metadata=True):
        self.home=Path(home or Path.home()).absolute()
        self.store=Path(store or self.home/'.local/share/desktop-looks').absolute()
        self.settings=settings or Settings()
        self.metadata=metadata

    @contextlib.contextmanager
    def lock(self):
        self.store.mkdir(parents=True,exist_ok=True,mode=0o700)
        with (self.store/'.lock').open('a') as f:
            fcntl.flock(f,fcntl.LOCK_EX)
            yield

    def profiles(self):
        result=[]
        if self.store.exists():
            for p in self.store.glob('*.look'):
                try:
                    with zipfile.ZipFile(p) as z: m=json.loads(z.read('manifest.json'))
                    result.append((p,m))
                except (ValueError,KeyError,zipfile.BadZipFile): continue
        return sorted(result,key=lambda item:item[1]['created'],reverse=True)

    def remap(self, value, source):
        return value.replace(source+'/',str(self.home)+'/') if isinstance(value,str) else value

    def vendor_launcher(self, name):
        roots=[self.home/'.local/share/flatpak/exports/share/applications']
        data_dirs=os.environ.get('XDG_DATA_DIRS') or '/usr/local/share:/usr/share'
        roots.extend(Path(root)/'applications' for root in data_dirs.split(':') if Path(root).is_absolute())
        roots.extend([Path('/usr/local/share/applications'),Path('/usr/share/applications'),
                      Path('/var/lib/flatpak/exports/share/applications'),
                      Path('/var/lib/snapd/desktop/applications')])
        roots=list(dict.fromkeys(roots))
        return next((root/name for root in roots if (root/name).is_file()),None)

    def permitted(self, rel, group, dependency=False):
        if group=='firefox':return firefox.allowed(rel)
        p=PurePosixPath(rel)
        if p.is_absolute() or '..' in p.parts or not p.parts: return False
        if dependency:
            if group=='icons' and re.fullmatch(r'\.local/share/Paradox Interactive/launcher-v2/cache/[A-Za-z0-9_-]+-appIcon',rel):return True
            return (p.parts[0] in ['Pictures','Documents','Downloads','Desktop','Music','Videos']
                    and p.suffix.lower() in ASSET_SUFFIXES)
        if rel in FIXED.get(group,[]): return True
        return any(rel==root or rel.startswith(root+'/') for root in TREES.get(group,[]))

    def dest(self, rel):
        p=PurePosixPath(rel)
        if rel == '.': return self.home
        if p.is_absolute() or '..' in p.parts or not p.parts: raise ValueError('Invalid profile path')
        dest=self.home/rel
        # Never follow pre-existing parent links outside this account.
        if not dest.parent.resolve().is_relative_to(self.home.resolve()):
            raise ValueError(f'Path points outside your home: {rel}')
        return dest

    def files_under(self, rel):
        base=self.home/rel
        if base.is_symlink() or base.is_file(): yield base; return
        if not base.is_dir(): return
        for root,dirs,files in os.walk(base,followlinks=False):
            dirs[:]=sorted(d for d in dirs if d not in ['.git','__pycache__',APPLET])
            for d in list(dirs):
                p=Path(root)/d
                if p.is_symlink(): yield p; dirs.remove(d)
            for f in sorted(files):
                if f.endswith(('.pyc','.log','.bak','~')): continue
                yield Path(root)/f

    def folder_icons(self):
        if not self.metadata: return {},[]
        from gi.repository import Gio
        roots=[self.home]
        pref=read_json(self.store/'folders.json') if (self.store/'folders.json').exists() else {}
        roots += [self.home/name for name in ['Desktop','Documents','Downloads','Pictures','Music','Videos'] if (self.home/name).is_dir()]
        roots += [self.home/p for p in pref.get('folders',[]) if not PurePosixPath(p).is_absolute() and '..' not in PurePosixPath(p).parts]
        paths=set(roots)
        excluded={'node_modules','.git','Steam','anaconda3','venv','.venv','work'}
        truncated=False
        for base in roots:
            if base==self.home: continue
            for root,dirs,_ in os.walk(base):
                depth=len(Path(root).relative_to(base).parts)
                dirs[:]=sorted(d for d in dirs if not d.startswith('.') and d not in excluded) if depth<2 else []
                paths.add(Path(root))
                if len(paths)>2000: truncated=True; break
            if truncated: break
        result={};warnings=[]
        if truncated: warnings.append('Folder icon scan reached 2,000 folders; add specific folders in Manage Looks to cover other locations.')
        for p in sorted(paths):
            try:
                info=Gio.File.new_for_path(str(p)).query_info('metadata::custom-icon,metadata::custom-icon-name',Gio.FileQueryInfoFlags.NONE,None)
                attrs={k:info.get_attribute_string(k) for k in ['metadata::custom-icon','metadata::custom-icon-name'] if info.has_attribute(k)}
                if attrs: result[str(p.relative_to(self.home))]=attrs
            except Exception as e: warnings.append(f'Could not read folder icon: {p.name}: {e}')
        return result,warnings

    def scan(self, name, groups):
        m={'format':'desktop-looks','version':1,'name':name,'created':dt.datetime.now(dt.timezone.utc).isoformat(),
           'source_home':str(self.home),'groups':sorted(groups),'files':[], 'settings':{},'json_patches':[],
           'app_icons':{},'app_window_classes':{},'desktop_icons':{},'folder_icons':{},'absent':[],'warnings':[]}
        sources={}
        def add(p,group,dependency=False):
            try: rel=str(p.relative_to(self.home))
            except ValueError:
                m['warnings'].append('External asset not bundled: '+str(p));return
            if rel.startswith('.local/share/icons/custom-apps/') and group=='desktop':return
            if rel in sources:return
            if not self.permitted(rel,group,dependency):
                if dependency:m['warnings'].append('Referenced asset outside supported asset folders was not bundled: '+rel)
                return
            if p.is_symlink():
                target=os.readlink(p)
                if not (p.parent/target).resolve().is_relative_to(self.home.resolve()):
                    m['warnings'].append('External symlink not bundled: '+rel);return
                sources[rel]=(p,{'path':rel,'group':group,'kind':'symlink','target':target,'dependency':dependency});return
            if p.is_file(): sources[rel]=(p,{'path':rel,'group':group,'kind':'file','dependency':dependency,'mode':p.stat().st_mode & 0o777})
        for group in groups:
            for root in TREES.get(group,[]):
                for p in self.files_under(root): add(p,group)
            for rel in FIXED.get(group,[]):
                p=self.home/rel
                if p.is_file(): add(p,group)
                else: m['absent'].append({'path':rel,'group':group})
        if 'desktop' in groups: m['settings']=self.settings.capture()
        if 'firefox' in groups:
            m['firefox'],extra=firefox.capture(self.home)
            for rel,p in extra.items():sources[rel]=(p,{'path':rel,'group':'firefox','kind':'file','mode':0o600})
            if 'Firefox' in self.running_apps(['firefox']):m['warnings'].append('Firefox is open; its appearance is captured from the last settings written to disk. Close it and save again for an exact snapshot.')
        if 'icons' in groups:
            for p in (self.home/'.local/share/applications').glob('*.desktop'):
                if p.is_file():
                    text=p.read_text(errors='replace')
                    m['app_icons'][p.name]=icon_line(text)
                    window_class=desktop_entry_value(text,'StartupWMClass')
                    if window_class:m['app_window_classes'][p.name]=window_class
            for p in (self.home/'Desktop').glob('*.desktop'):
                if p.is_file(): m['desktop_icons'][p.name]=icon_line(p.read_text(errors='replace'))
            m['folder_icons'],warnings=self.folder_icons();m['warnings']+=warnings
        if 'steam' in groups:
            rel='.config/millennium/config.json';d=read_json(self.home/rel)
            if d:
                m['json_patches'].append({'path':rel,'group':'steam','values':{'themes':d.get('themes',{}),
                    'general':{k:d.get('general',{}).get(k) for k in ['accentColor','injectCSS','injectJavascript'] if k in d.get('general',{})}}})
        if 'discord' in groups:
            for rel in ['.config/Vencord/settings/settings.json','.var/app/com.discordapp.Discord/config/Vencord/settings/settings.json']:
                d=read_json(self.home/rel)
                if d: m['json_patches'].append({'path':rel,'group':'discord','values':{k:d[k] for k in VC_KEYS if k in d}})
        # Include referenced icons, wallpapers, CSS and fonts kept outside the usual theme folders.
        refs=[(m['settings'],'desktop'),(m['app_icons'],'icons'),(m['desktop_icons'],'icons'),(m['folder_icons'],'icons')]
        for group in groups:
            for p,item in list(sources.values()):
                if item['group']==group and group!='firefox' and p.suffix in TEXT_SUFFIXES and not p.is_symlink() and p.stat().st_size<2_000_000:
                    refs.append((p.read_text(errors='replace'),group))
        for value,group in refs:
            raw=json.dumps(value,ensure_ascii=False)
            # JSON-escaped strings are decoded individually so paths with spaces survive.
            strings=[raw] if isinstance(value,str) else []
            def walk(v):
                if isinstance(v,str): strings.append(v)
                elif isinstance(v,dict):
                    for x in v.values():walk(x)
                elif isinstance(v,list):
                    for x in v:walk(x)
            walk(value)
            for s in strings:
                from urllib.parse import unquote
                s=unquote(s)
                for match in re.finditer(re.escape(str(self.home)) + r'/[^\n\r\"\'<>\)]+',s):
                    path=Path(match.group(0).strip())
                    if path.is_file(): add(path,group,True)
                # Exact icon paths are common, and may contain apostrophes.
                if s.startswith(str(self.home)+'/') and Path(s).is_file(): add(Path(s),group,True)
        m['files']=[item for p,item in sources.values()]
        m['summary']={'files':len(sources),'folder_icons':len(m['folder_icons']),'app_icons':len(m['app_icons']),
                      'desktop_icons':len(m['desktop_icons']),'settings':sum(len(v) for v in m['settings'].values())}
        return m,sources

    def capture(self, name, groups=None, output=None):
        groups=set(GROUPS if groups is None else groups)
        if not groups: raise ValueError('Select at least one component')
        if not groups <= GROUPS.keys(): raise ValueError('Unknown appearance component')
        with self.lock(): return self._capture(name,groups,output)

    def _capture(self, name, groups, output=None):
        manifest,sources=self.scan(name,groups)
        slug=re.sub(r'[^a-z0-9]+','-',name.lower()).strip('-')[:50] or 'look'
        target=Path(output) if output else self.store/f'{slug}-{uuid.uuid4().hex[:8]}.look'
        target.parent.mkdir(parents=True,exist_ok=True)
        fd,tmp=tempfile.mkstemp(dir=target.parent,suffix='.partial');os.close(fd)
        try:
            with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED,compresslevel=5) as z:
                for rel,(p,item) in sources.items():
                    if item['kind']=='file': z.write(p,'payload/'+rel)
                z.writestr('manifest.json',json.dumps(manifest,indent=2,ensure_ascii=False))
            os.chmod(tmp,0o600);os.replace(tmp,target)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        return target,manifest

    def inspect(self, path):
        with zipfile.ZipFile(path) as z:
            if sum(i.file_size for i in z.infolist())>2_000_000_000: raise ValueError('Profile exceeds 2 GB')
            if z.getinfo('manifest.json').file_size>10_000_000:raise ValueError('Profile manifest is too large')
            m=json.loads(z.read('manifest.json'))
            if m.get('format')!='desktop-looks' or m.get('version')!=1: raise ValueError('Unsupported profile format')
            if not set(m['groups'])<=GROUPS.keys():raise ValueError('Unknown component in profile')
            for item in m['files']:
                if not self.permitted(item['path'],item['group'],item.get('dependency',False)):raise ValueError('Unsupported asset path: '+item['path'])
                if item['group']!='firefox':self.dest(item['path'])
                if item['kind']=='file':z.getinfo('payload/'+item['path'])
                elif item['kind']=='symlink':
                    target=self.remap(item['target'],m['source_home'])
                    if not (self.dest(item['path']).parent/target).resolve().is_relative_to(self.home.resolve()):raise ValueError('External symlink in profile')
                else:raise ValueError('Unsupported asset type')
            for item in m['absent']:
                if item['path'] not in FIXED.get(item['group'],[]):raise ValueError('Invalid optional file')
                self.dest(item['path'])
            allowed_json={'.config/millennium/config.json','.config/Vencord/settings/settings.json','.var/app/com.discordapp.Discord/config/Vencord/settings/settings.json'}
            for item in m['json_patches']:
                if item['path'] not in allowed_json:raise ValueError('Invalid app settings path')
                allowed={'themes','general'} if item['group']=='steam' else set(VC_KEYS)
                if not set(item['values'])<=allowed:raise ValueError('Non-appearance app setting in profile')
                if item['group']=='steam' and not set(item['values'].get('general',{}))<={'accentColor','injectCSS','injectJavascript'}:raise ValueError('Non-appearance Steam setting')
                self.dest(item['path'])
            for field,root in [('app_icons','.local/share/applications'),('desktop_icons','Desktop')]:
                for name,icon in m.get(field,{}).items():
                    if icon is not None and (not isinstance(icon,str) or '\n' in icon or '\r' in icon):raise ValueError('Invalid icon value')
                    if Path(name).name!=name or not name.endswith('.desktop'):raise ValueError('Invalid launcher filename')
                    self.dest(root+'/'+name)
            for name,value in m.get('app_window_classes',{}).items():
                if name not in m['app_icons']:raise ValueError('Window class has no saved app launcher')
                if not isinstance(value,str) or not value or len(value)>256 or any(c in value for c in '\n\r\0'):
                    raise ValueError('Invalid launcher window class')
            for rel,attrs in m['folder_icons'].items():
                self.dest(rel)
                if not set(attrs)<={'metadata::custom-icon','metadata::custom-icon-name'}:raise ValueError('Invalid folder metadata')
            for schema,keys in m['settings'].items():
                if schema not in SCHEMAS and schema!='org.cinnamon':raise ValueError('Unsupported settings schema')
                if schema=='org.cinnamon' and any(k not in ROOT_KEYS and not k.startswith(ROOT_PREFIXES) for k in keys):raise ValueError('Unsupported Cinnamon setting')
                if schema in SCHEMAS and SCHEMAS[schema] is not None and not set(keys)<=set(SCHEMAS[schema]):raise ValueError('Unsupported appearance setting')
            firefox.validate(m.get('firefox'),z,m['files'])
        return m

    def running_apps(self, groups):
        if not ({'steam','discord','firefox'} & set(groups)):return []
        found=set()
        # Read process names only, without command arguments or account data.
        for p in Path('/proc').glob('[0-9]*'):
            try:
                if p.stat().st_uid!=os.getuid():continue
                name=(p/'comm').read_text().strip().lower()
                if 'steam' in groups and name in ['steam','steamwebhelper']:found.add('Steam')
                if 'discord' in groups and name in ['discord','discordcanary','discordptb']:found.add('Discord')
                if 'firefox' in groups and name in ['firefox','firefox-bin']:found.add('Firefox')
            except (OSError,PermissionError):pass
        return sorted(found)

    def import_profile(self, path):
        m=self.inspect(path)
        with self.lock():
            target=self.store/f'imported-{uuid.uuid4().hex[:8]}.look'
            shutil.copyfile(path,target);target.chmod(0o600)
        return target,m

    def restore(self, path, groups=None):
        m=self.inspect(path);groups=set(m['groups'] if groups is None else groups) & set(m['groups'])
        if not groups:raise ValueError('Select at least one saved component')
        running=self.running_apps(groups)
        if running:raise RuntimeError('Close '+', '.join(running)+' completely, then apply this look again.')
        with self.lock():
            recovery,previous=self._capture('Recovery before '+m['name'],groups)
            try:
                warnings=self._apply(path,m,groups,previous)
            except Exception as e:
                try:self._apply(recovery,previous,groups,m)
                except Exception as rollback:raise RuntimeError(f'Apply failed: {e}. Recovery also needs attention: {rollback}. Saved recovery: {recovery}') from e
                raise RuntimeError(f'Apply failed and previous appearance was restored: {e}. Recovery: {recovery}') from e
            (self.store/'active.json').write_text(json.dumps({'name':m['name'],'recovery':str(recovery),'groups':sorted(groups)}))
        return recovery,warnings

    def write(self, path, data, mode=0o600):
        path.parent.mkdir(parents=True,exist_ok=True)
        fd,tmp=tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(fd,'wb') as f:f.write(data)
            os.chmod(tmp,mode & 0o777);os.replace(tmp,path)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)

    def _apply(self, archive, m, groups, previous):
        source=m['source_home'];remap=lambda s:self.remap(s,source)
        warnings=[]
        with zipfile.ZipFile(archive) as z:
            for item in m['files']:
                if item['group'] not in groups or item['group']=='firefox':continue
                dest=self.dest(item['path'])
                if item['kind']=='symlink':
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    if dest.is_dir() and not dest.is_symlink():raise ValueError('A folder blocks the saved link: '+item['path'])
                    if dest.exists() or dest.is_symlink():dest.unlink()
                    dest.symlink_to(remap(item['target']));continue
                data=z.read('payload/'+item['path'])
                if dest.suffix.lower() in TEXT_SUFFIXES or dest.name in ['.gtkrc-2.0','index.theme']:
                    try:data=remap(data.decode()).encode()
                    except UnicodeDecodeError:pass
                self.write(dest,data,item.get('mode',0o600))
        for item in m['absent']:
            if item['group'] in groups:
                dest=self.dest(item['path'])
                if dest.is_file() or dest.is_symlink():dest.unlink()
        for patch in m['json_patches']:
            if patch['group'] not in groups:continue
            path=self.dest(patch['path']);d=read_json(path)
            values=json.loads(remap(json.dumps(patch['values'],ensure_ascii=False)))
            if patch['group']=='steam':
                for k in ['accentColor','injectCSS','injectJavascript']:d.setdefault('general',{}).pop(k,None)
                d.setdefault('general',{}).update(values.get('general',{}));d['themes']=values.get('themes',{})
            else:
                for k in VC_KEYS:d.pop(k,None)
                d.update(values)
            self.write(path,(json.dumps(d,indent=2,ensure_ascii=False)+'\n').encode())
        if 'icons' in groups:
            effective={}
            for name in sorted(set(m['app_icons'])|set(previous.get('app_icons',{}))):
                dest=self.dest('.local/share/applications/'+name)
                vendor=self.vendor_launcher(name)
                if name in m['app_icons']:
                    icon=m['app_icons'][name]
                elif vendor:
                    # A launcher added since this snapshot must not retain the last look's override.
                    icon=icon_line(vendor.read_text())
                else:
                    warnings.append('No installed default for newer launcher; kept icon: '+name);continue
                base=dest if dest.is_file() else vendor
                if base is None:
                    warnings.append('Launcher not installed here; skipped icon: '+name);continue
                effective[name]=remap(icon) if icon is not None else None
                text=change_icon(base.read_text(),effective[name])
                if name in m.get('app_window_classes',{}):
                    text=change_window_class(text,m['app_window_classes'][name])
                self.write(dest,text.encode(),0o644)
            # Old profiles saved menu icons only. Match existing desktop shortcuts by filename;
            # new profiles preserve their independent icon assignments, without copying commands.
            desktop_icons=m.get('desktop_icons',effective)
            for name in sorted(set(desktop_icons)|set(previous.get('desktop_icons',{}))):
                dest=self.dest('Desktop/'+name)
                if not dest.is_file():continue
                if name in desktop_icons:icon=desktop_icons[name]
                elif name in effective:icon=effective[name]
                else:
                    vendor=self.vendor_launcher(name)
                    if vendor is None:continue
                    icon=icon_line(vendor.read_text())
                self.write(dest,change_icon(dest.read_text(),remap(icon) if icon is not None else None).encode(),dest.stat().st_mode)
            if self.metadata:
                from gi.repository import Gio
                # Clear old profile-specific folder icons as well as restoring saved assignments.
                for rel in set(previous.get('folder_icons',{}))|set(m['folder_icons']):
                    dest=self.dest(rel)
                    if not dest.exists():continue
                    attrs=m['folder_icons'].get(rel,{})
                    info=Gio.FileInfo()
                    for attr in ['metadata::custom-icon','metadata::custom-icon-name']:
                        if attr in attrs:info.set_attribute_string(attr,remap(attrs[attr]))
                        else:info.set_attribute(attr,Gio.FileAttributeType.INVALID,0)
                    try:
                        ok,_=Gio.File.new_for_path(str(dest)).set_attributes_from_info(info,Gio.FileQueryInfoFlags.NONE,None)
                        if not ok:raise RuntimeError('metadata service did not accept the icon')
                    except Exception as e:warnings.append('Folder icon could not be applied: '+str(dest)+': '+str(e))
        if 'firefox' in groups:
            with zipfile.ZipFile(archive) as z:warnings+=firefox.restore(self.home,z,m.get('firefox'),m['files'],self.write,remap)
        if 'desktop' in groups:warnings+=self.settings.apply(m['settings'],remap)
        return warnings


def gui(manager):
    import gi
    gi.require_version('Gtk','3.0')
    from gi.repository import Gtk,GLib
    import threading
    class Window(Gtk.Window):
        def __init__(self):
            super().__init__(title='Desktop Looks');self.set_default_size(1000,610);self.set_border_width(20)
            self.connect('destroy',Gtk.main_quit)
            box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);self.add(box)
            title=Gtk.Label();title.set_markup('<big><b>Your whole desktop, saved as a look</b></big>');title.set_xalign(0);box.pack_start(title,False,False,0)
            subtitle=Gtk.Label(label='Save themes, Classic Menu, icon overrides, Steam and Discord together.');subtitle.set_xalign(0);subtitle.set_line_wrap(True);box.pack_start(subtitle,False,False,0)
            self.list=Gtk.ListBox();self.list.set_selection_mode(Gtk.SelectionMode.SINGLE)
            scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC);scroll.add(self.list);box.pack_start(scroll,True,True,0)
            self.checks={};row=Gtk.Grid(column_spacing=18,row_spacing=6)
            for index,(group,label) in enumerate(GROUPS.items()):
                c=Gtk.CheckButton(label=label);c.set_active(True);self.checks[group]=c;row.attach(c,index%3,index//3,1,1)
            box.pack_start(row,False,False,0)
            self.controls=Gtk.Box(spacing=8);box.pack_start(self.controls,False,False,0)
            for label,fn in [('Save current look…',self.save),('Apply selected',self.apply),('Import…',self.import_),('Export…',self.export),('Track folder icons…',self.track)]:
                b=Gtk.Button(label=label);b.connect('clicked',fn);self.controls.pack_start(b,False,False,0)
            self.status=Gtk.Label(label='A recovery look is saved automatically before every apply.');self.status.set_xalign(0);self.status.set_line_wrap(True);box.pack_start(self.status,False,False,0)
            note=Gtk.Label(label='Close the selected apps before applying their themes. Firefox uses a brief offline session to activate its theme. Log out and back in after restoring panels, desklets or desktop icon layout.');note.set_xalign(0);note.set_line_wrap(True);box.pack_start(note,False,False,0)
            self.refresh()
        def selected(self):
            r=self.list.get_selected_row()
            if not r:raise ValueError('Select a saved look first.')
            return r.path,r.manifest
        def groups(self):return [g for g,c in self.checks.items() if c.get_active()]
        def refresh(self):
            for child in self.list.get_children():self.list.remove(child)
            for path,m in manager.profiles():
                r=Gtk.ListBoxRow();r.path=path;r.manifest=m
                text=f"{m['name']}\n{m['created'][:16].replace('T',' ')} UTC · {', '.join(m['groups'])} · {path.stat().st_size/1e6:.1f} MB"
                if 'discord' in m['groups']:text+='\n'+discord_theme_summary(m)
                label=Gtk.Label(label=text);label.set_xalign(0);label.set_margin_top(8);label.set_margin_bottom(8);label.set_margin_start(8);r.add(label);self.list.add(r)
            self.list.show_all()
        def error(self,e):
            d=Gtk.MessageDialog(transient_for=self,modal=True,message_type=Gtk.MessageType.ERROR,buttons=Gtk.ButtonsType.CLOSE,text=str(e));d.run();d.destroy()
        def busy(self,description,fn):
            self.controls.set_sensitive(False);self.status.set_text(description)
            def work():
                try:result=fn();GLib.idle_add(done,result,None)
                except Exception as e:GLib.idle_add(done,None,e)
            def done(result,error):
                self.controls.set_sensitive(True);self.refresh()
                if error:self.status.set_text('No look was applied successfully.');self.error(error)
                else:self.status.set_text(result)
                return False
            threading.Thread(target=work,daemon=True).start()
        def save(self,_):
            d=Gtk.Dialog(title='Save current look',transient_for=self,modal=True);d.add_buttons('Cancel',Gtk.ResponseType.CANCEL,'Save',Gtk.ResponseType.OK)
            e=Gtk.Entry();e.set_placeholder_text('For example: Windows 95, Friends, or Mint');e.set_margin_top(16);e.set_margin_bottom(16);e.set_margin_start(16);e.set_margin_end(16);d.get_content_area().add(e);d.show_all();response=d.run();name=e.get_text().strip();d.destroy()
            if response!=Gtk.ResponseType.OK or not name:return
            groups=self.groups()
            if not groups:self.error(ValueError('Choose at least one component.'));return
            def task():
                p,m=manager.capture(name,groups);return f"Saved {name}: {m['summary']['files']} files, {m['summary']['app_icons']} app icons, {m['summary']['folder_icons']} folder icon assignments."+(' '+str(len(m['warnings']))+' items need attention; see the profile manifest.' if m['warnings'] else '')
            self.busy('Saving appearance assets…',task)
        def apply(self,_):
            try:path,m=self.selected()
            except Exception as e:self.error(e);return
            groups=self.groups()
            d=Gtk.MessageDialog(transient_for=self,modal=True,message_type=Gtk.MessageType.QUESTION,buttons=Gtk.ButtonsType.OK_CANCEL,text='Apply '+m['name']+'?')
            detail='The selected appearance components will be restored. A recovery look will be saved first. Panels and applets may require logging out and back in.'
            if 'discord' in groups and 'discord' in m['groups']:detail+='\n\n'+discord_theme_summary(m)
            d.format_secondary_text(detail);r=d.run();d.destroy()
            if r!=Gtk.ResponseType.OK:return
            def task():
                recovery,warnings=manager.restore(path,groups)
                return f'Applied {m["name"]}. Recovery saved. Log out and back in to refresh panels and applets.'+(' '+ '; '.join(warnings[:3]) if warnings else '')
            self.busy('Saving recovery and applying look…',task)
        def choose(self,title,action):
            d=Gtk.FileChooserDialog(title=title,transient_for=self,action=action);d.add_buttons('Cancel',Gtk.ResponseType.CANCEL,'Choose',Gtk.ResponseType.OK)
            if action!=Gtk.FileChooserAction.SELECT_FOLDER:
                f=Gtk.FileFilter();f.set_name('Desktop Looks profiles');f.add_pattern('*.look');d.add_filter(f)
            r=d.run();path=d.get_filename();d.destroy();return path if r==Gtk.ResponseType.OK else None
        def import_(self,_):
            path=self.choose('Import a trusted look',Gtk.FileChooserAction.OPEN)
            if not path:return
            def task():
                p,m=manager.import_profile(path);return 'Imported '+m['name']+'. Select it and choose Apply when ready.'
            self.busy('Importing look…',task)
        def export(self,_):
            try:path,m=self.selected()
            except Exception as e:self.error(e);return
            dest=self.choose('Export look',Gtk.FileChooserAction.SAVE)
            if not dest:return
            if not dest.endswith('.look'):dest+='.look'
            try:shutil.copyfile(path,dest);self.status.set_text('Exported '+dest)
            except Exception as e:self.error(e)
        def track(self,_):
            path=self.choose('Track folder icons here and two levels below',Gtk.FileChooserAction.SELECT_FOLDER)
            if not path:return
            try:
                rel=str(Path(path).relative_to(manager.home));manager.dest(rel)
                with manager.lock():
                    p=manager.store/'folders.json';d=read_json(p);d['folders']=sorted(set(d.get('folders',[])+[rel]));p.write_text(json.dumps(d,indent=2))
                self.status.set_text('Folder added. Save a new look to include its icon assignments.')
            except ValueError:self.error(ValueError('Choose a folder within your own home folder.'))
    w=Window();w.show_all();Gtk.main()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--home');p.add_argument('--store')
    sub=p.add_subparsers(dest='command');sub.add_parser('gui');sub.add_parser('list')
    c=sub.add_parser('capture');c.add_argument('name');c.add_argument('--output');c.add_argument('--groups',nargs='+',choices=GROUPS)
    c=sub.add_parser('inspect');c.add_argument('profile')
    c=sub.add_parser('restore');c.add_argument('profile');c.add_argument('--groups',nargs='+',choices=GROUPS);c.add_argument('--yes',action='store_true')
    c=sub.add_parser('import');c.add_argument('profile')
    a=p.parse_args();m=Looks(a.home,a.store)
    try:
        if a.command in [None,'gui']:gui(m)
        elif a.command=='capture':
            path,manifest=m.capture(a.name,a.groups,a.output);print(json.dumps({'path':str(path),'summary':manifest['summary'],'warnings':manifest['warnings']},indent=2))
        elif a.command=='inspect':print(json.dumps(m.inspect(a.profile),indent=2))
        elif a.command=='list':print(json.dumps([{'path':str(path),'name':v['name'],'created':v['created']} for path,v in m.profiles()],indent=2))
        elif a.command=='import':print(m.import_profile(a.profile)[0])
        elif a.command=='restore':
            if not a.yes:raise ValueError('Use the applet to review the look, or add --yes to apply it from the command line.')
            recovery,warnings=m.restore(a.profile,a.groups);print(json.dumps({'recovery':str(recovery),'warnings':warnings},indent=2))
    except Exception as e:print(str(e),file=sys.stderr);return 1
    return 0

if __name__=='__main__':sys.exit(main())
