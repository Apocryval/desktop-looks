"""Reproduce known portability gaps in disposable homes, not installed apps.

Run directly; --require-all exits nonzero while any scenario is unsupported.
"""
import argparse
import inspect
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop-looks@local'))
import looks as L


def write(home,rel,text):
    p=home/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text);return p


def probe():
    results=[]
    def record(name,works,observation):
        results.append({'scenario':name,'supported':bool(works),'observation':observation})
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        home=root/'localized';home.mkdir()
        write(home,'.config/user-dirs.dirs','XDG_DESKTOP_DIR="$HOME/Bureau"\n')
        write(home,'Bureau/editor.desktop','[Desktop Entry]\nIcon=editor\nExec=editor\n')
        _,m=L.Looks(home,metadata=False).capture('localized',['icons'])
        record('localized-desktop-directory','editor.desktop' in m['desktop_icons'],
               'Configured Bureau shortcut is omitted; capture scans Desktop only.')
        home=root/'xdg';home.mkdir()
        write(home,'custom-config/Vencord/settings/settings.json',json.dumps({'enabledThemes':['test.css']}))
        with patch.dict(os.environ,{'XDG_CONFIG_HOME':str(home/'custom-config')}):
            _,m=L.Looks(home,metadata=False).capture('xdg',['discord'])
        record('custom-xdg-config-home',any(p['group']=='discord' for p in m['json_patches']),
               'Vencord settings in a nondefault XDG_CONFIG_HOME are omitted.')
        home=root/'donor';home.mkdir()
        write(home,'.config/Vencord/settings/settings.json',json.dumps({'enabledThemes':['test.css']}))
        write(home,'.config/Vencord/themes/test.css','/* fixture */')
        archive,_=L.Looks(home,metadata=False).capture('native',['discord'])
        receiver=root/'flatpak';receiver.mkdir()
        target=write(receiver,'.var/app/com.discordapp.Discord/config/Vencord/settings/settings.json',json.dumps({'enabledThemes':[]}))
        manager=L.Looks(receiver,metadata=False);manager.running_apps=lambda groups:[]
        manager.restore(archive,['discord'])
        record('native-to-flatpak-discord',json.loads(target.read_text())['enabledThemes']==['test.css'],
               'Restore writes donor native path; existing Flatpak selection stays unchanged.')
        home=root/'missing';home.mkdir()
        write(home,'.config/Vencord/settings/settings.json',json.dumps({'enabledThemes':['missing.theme.css']}))
        manager=L.Looks(home,metadata=False);archive,_=manager.capture('missing',['discord'])
        rejected=False
        try:manager.inspect(archive)
        except ValueError:rejected=True
        record('missing-selected-theme-preflight',rejected,
               'Validation accepts a selected local theme whose CSS was never bundled.')
        home=root/'profiles';home.mkdir()
        for name in ['personal','work']:(home/'.mozilla/firefox'/name).mkdir(parents=True)
        write(home,'.mozilla/firefox/profiles.ini','[Profile0]\nName=personal\nPath=personal\nIsRelative=1\nDefault=1\n[Profile1]\nName=work\nPath=work\nIsRelative=1\n')
        selected=L.firefox.profile(home)
        selector_parameters=set(inspect.signature(L.firefox.profile).parameters)-{'home'}
        record('explicit-firefox-profile-selection',bool(selector_parameters),
               'Resolver selects '+selected.name+' automatically; API has no explicit profile selector.')
        home=root/'online';home.mkdir()
        write(home,'.config/Vencord/settings/settings.json',json.dumps({'enabledThemes':['online.css']}))
        write(home,'.config/Vencord/themes/online.css','@import url("https://example.invalid/theme.css");')
        archive,m=L.Looks(home,metadata=False).capture('online',['discord'])
        with zipfile.ZipFile(archive) as z:
            wrappers=[z.read('payload/'+f['path']) for f in m['files'] if f['path'].endswith('online.css')]
        record('offline-remote-css-dependencies',not any(b'https://' in content for content in wrappers),
               'CSS wrapper is bundled; its remote dependency still requires network access.')
    return {'regression_suite':'run unittest discover separately','probes':results,
            'supported':sum(r['supported'] for r in results),'unsupported':sum(not r['supported'] for r in results)}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--require-all',action='store_true');args=parser.parse_args()
    result=probe();print(json.dumps(result,indent=2))
    sys.exit(1 if args.require_all and result['unsupported'] else 0)
