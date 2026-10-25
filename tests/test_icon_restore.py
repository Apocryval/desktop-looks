import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'desktop-looks@local'))
import looks as L


class IconRestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home=pathlib.Path(self.temp.name)/'home'
        self.home.mkdir()
        self.manager=L.Looks(self.home,metadata=False)

    def launcher(self,rel,icon,extra=''):
        p=self.home/rel
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text('[Desktop Entry]\nName=Test\nExec=keep-this --flag\nIcon='+icon+'\nIcon[en_GB]='+icon+'\n'+extra)
        return p

    def test_desktop_icons_capture_restore_and_keep_exec_and_mode(self):
        p=self.launcher('Desktop/steam.desktop','desktop-custom')
        p.chmod(0o755)
        self.launcher('.local/share/applications/steam.desktop','menu-custom')
        archive,m=self.manager.capture('test',['icons'])
        self.assertEqual(m['desktop_icons']['steam.desktop'],'desktop-custom')
        self.launcher('Desktop/steam.desktop','wrong')
        self.manager.restore(archive,['icons'])
        self.assertEqual(L.icon_line(p.read_text()),'desktop-custom')
        self.assertIn('Icon[en_GB]=desktop-custom',p.read_text())
        self.assertIn('Exec=keep-this --flag',p.read_text())
        self.assertEqual(p.stat().st_mode & 0o777,0o755)

    def test_newer_launcher_resets_to_vendor_and_recovery_restores_override(self):
        archive,_=self.manager.capture('before install',['icons'])
        p=self.launcher('.local/share/applications/nordvpn.desktop','steam95')
        vendor=self.launcher('vendor/nordvpn.desktop','nordvpn')
        with patch.object(self.manager,'vendor_launcher',return_value=vendor):
            recovery,warnings=self.manager.restore(archive,['icons'])
            self.assertFalse(warnings)
            self.assertEqual(L.icon_line(p.read_text()),'nordvpn')
            self.manager.restore(recovery,['icons'])
            self.assertEqual(L.icon_line(p.read_text()),'steam95')
        self.assertIn('Exec=keep-this --flag',p.read_text())

    def test_snap_launcher_is_used_when_no_local_override_exists(self):
        self.launcher('.local/share/applications/nordvpn_nordvpn-gui.desktop','custom')
        archive,_=self.manager.capture('test',['icons'])
        (self.home/'.local/share/applications/nordvpn_nordvpn-gui.desktop').unlink()
        original=pathlib.Path.is_file
        snap=pathlib.Path('/var/lib/snapd/desktop/applications/nordvpn_nordvpn-gui.desktop')
        with patch.object(pathlib.Path,'is_file',lambda p: p==snap or original(p)):
            self.assertEqual(self.manager.vendor_launcher(snap.name),snap)

    def test_legacy_profile_updates_matching_desktop_shortcut(self):
        self.launcher('.local/share/applications/steam.desktop','steam')
        shortcut=self.launcher('Desktop/steam.desktop','steam95')
        archive,m=self.manager.capture('test',['icons'])
        m.pop('desktop_icons')
        self.manager._apply(archive,m,{'icons'},{})
        self.assertEqual(L.icon_line(shortcut.read_text()),'steam')
        self.assertIn('Icon[en_GB]=steam',shortcut.read_text())

    def test_desktop_only_icon_asset_is_bundled(self):
        asset=self.home/'Pictures/shortcut.png'
        asset.parent.mkdir()
        asset.write_bytes(b'PNG')
        self.launcher('Desktop/test.desktop',str(asset))
        _,m=self.manager.capture('test',['icons'])
        self.assertIn('Pictures/shortcut.png',[f['path'] for f in m['files']])

    def test_desktop_path_escape_is_rejected(self):
        import zipfile
        archive,m=self.manager.capture('test',['icons'])
        m['desktop_icons']={'../outside.desktop':'bad'}
        bad=self.home/'bad.look'
        with zipfile.ZipFile(bad,'w') as z:z.writestr('manifest.json',json.dumps(m))
        with self.assertRaisesRegex(ValueError,'launcher filename'):
            self.manager.inspect(bad)

if __name__=='__main__':unittest.main()
