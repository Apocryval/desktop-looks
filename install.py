#!/usr/bin/python3
from pathlib import Path
import shutil, subprocess, sys
root=Path(__file__).resolve().parent
home=Path.home()
target=home/'.local/share/cinnamon/applets/desktop-looks@local'
target.parent.mkdir(parents=True,exist_ok=True)
if target.exists():
    raise SystemExit('Desktop Looks is already installed. Run update-installed.sh to perform the approved asset migration and update the existing applet.')
shutil.copytree(root/'desktop-looks@local',target,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
profiles=home/'.local/share/desktop-looks';profiles.mkdir(parents=True,exist_ok=True,mode=0o700)
for p in root.glob('*.look'):
    subprocess.run(['/usr/bin/python3',str(target/'looks.py'),'import',str(p)],check=True)
print('Installed Desktop Looks. Open System Settings → Applets, find Desktop Looks, and click + to add it to a panel.')
subprocess.Popen(['cinnamon-settings','applets'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
