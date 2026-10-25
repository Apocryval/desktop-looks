"""Synthetic app/layout tests; never inspect or modify the user's applications."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop-looks@local'))
import looks as L


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name)/'donor'
        self.home.mkdir()
        self.m=L.Looks(self.home,metadata=False)
        self.m.running_apps=lambda groups:[]

    def write(self,rel,text):
        p=self.home/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text);return p

    def launcher(self,name='org.example.Editor.desktop',icon='editor'):
        return self.write('.local/share/applications/'+name,
            '[Desktop Entry]\nName=Editor\nExec=editor --private-option %U\nIcon='+icon+
            '\nIcon[de]=localized\nStartupWMClass=ExampleEditor\nActions=New;\n'
            '[Desktop Action New]\nName=New\nExec=editor --new-window\nIcon=document-new\n')

    def test_vendor_package_layout_matrix(self):
        name='org.example.Editor.desktop'
        roots=['/usr/local/share/applications','/usr/share/applications',
               '/var/lib/flatpak/exports/share/applications',
               str(self.home/'.local/share/flatpak/exports/share/applications'),
               '/var/lib/snapd/desktop/applications','/opt/example/share/applications']
        for root in roots:
            with self.subTest(root=root):
                expected=Path(root)/name
                with patch.dict(os.environ,{'XDG_DATA_DIRS':'/opt/example/share:/usr/share'}), \
                     patch.object(Path,'is_file',lambda p:p==expected):
                    self.assertEqual(self.m.vendor_launcher(name),expected)

    def test_local_system_package_precedes_distribution_package(self):
        name='editor.desktop';candidates={Path('/usr/share/applications')/name,Path('/usr/local/share/applications')/name}
        with patch.dict(os.environ,{'XDG_DATA_DIRS':''}),patch.object(Path,'is_file',lambda p:p in candidates):
            self.assertEqual(self.m.vendor_launcher(name),Path('/usr/local/share/applications')/name)

    def test_user_flatpak_precedes_system_flatpak(self):
        name='editor.desktop';user=self.home/'.local/share/flatpak/exports/share/applications'/name
        system=Path('/var/lib/flatpak/exports/share/applications')/name
        with patch.object(Path,'is_file',lambda p:p in {user,system}):
            self.assertEqual(self.m.vendor_launcher(name),user)

    def test_configured_vendor_root_precedence(self):
        name='editor.desktop';first=Path('/opt/a/share/applications')/name;second=Path('/opt/b/share/applications')/name
        with patch.dict(os.environ,{'XDG_DATA_DIRS':'/opt/b/share:/opt/a/share'}),patch.object(Path,'is_file',lambda p:p in {first,second}):
            self.assertEqual(self.m.vendor_launcher(name),second)

    def test_relative_vendor_root_is_ignored(self):
        with patch.dict(os.environ,{'XDG_DATA_DIRS':'relative/path'}),patch.object(Path,'is_file',lambda p:not p.is_absolute()):
            self.assertIsNone(self.m.vendor_launcher('editor.desktop'))

    def test_window_class_capture_and_cross_account_restore(self):
        self.launcher();archive,m=self.m.capture('Editor',['icons'])
        self.assertEqual(m['app_window_classes'],{'org.example.Editor.desktop':'ExampleEditor'})
        target=self.home.parent/'receiver';target.mkdir()
        other=L.Looks(target,metadata=False)
        other.running_apps=lambda groups:[]
        dest=target/'.local/share/applications/org.example.Editor.desktop'
        dest.parent.mkdir(parents=True)
        dest.write_text('[Desktop Entry]\nExec=receiver-editor --keep-this\nIcon=receiver\n')
        other.restore(archive,['icons'])
        text=dest.read_text()
        self.assertEqual(L.desktop_entry_value(text,'StartupWMClass'),'ExampleEditor')
        self.assertIn('Exec=receiver-editor --keep-this',text)

    def test_legacy_profile_preserves_receivers_window_class(self):
        p=self.launcher();archive,m=self.m.capture('Legacy',['icons'])
        m.pop('app_window_classes')
        p.write_text(p.read_text().replace('ExampleEditor','ReceiverEditor'))
        self.m._apply(archive,m,{'icons'},{})
        self.assertEqual(L.desktop_entry_value(p.read_text(),'StartupWMClass'),'ReceiverEditor')

    def test_window_class_edit_leaves_actions_and_commands_untouched(self):
        p=self.launcher();text=p.read_text()+'StartupWMClass=ActionClass\n'
        result=L.change_window_class(text,'NewEditor')
        self.assertIn('Exec=editor --private-option %U',result)
        self.assertIn('[Desktop Action New]\nName=New\nExec=editor --new-window\nIcon=document-new\nStartupWMClass=ActionClass',result)
        self.assertEqual(L.desktop_entry_value(result,'StartupWMClass'),'NewEditor')

    def test_window_class_is_added_before_desktop_actions(self):
        text='[Desktop Entry]\nExec=editor\n[Desktop Action New]\nExec=editor --new\n'
        changed=L.change_window_class(text,'Editor')
        self.assertIn('StartupWMClass=Editor\n[Desktop Action New]',changed)

    def test_icon_restore_preserves_desktop_action_icon(self):
        text=self.launcher().read_text()
        changed=L.change_icon(text,'modern-editor')
        self.assertEqual(L.icon_line(changed),'modern-editor')
        self.assertIn('Icon[de]=modern-editor',changed)
        self.assertIn('Icon=document-new',changed)

    def test_null_icon_removes_localized_override_but_keeps_action(self):
        changed=L.change_icon(self.launcher().read_text(),None)
        self.assertIsNone(L.icon_line(changed))
        self.assertNotIn('Icon[de]=',changed)
        self.assertIn('Icon=document-new',changed)

    def test_missing_application_warns_without_creating_launcher(self):
        p=self.launcher();archive,_=self.m.capture('test',['icons']);p.unlink()
        with patch.object(self.m,'vendor_launcher',return_value=None):
            _,warnings=self.m.restore(archive,['icons'])
        self.assertTrue(any('not installed' in w for w in warnings))
        self.assertFalse(p.exists())

    def test_new_private_launcher_keeps_icon_when_no_vendor_default_exists(self):
        archive,_=self.m.capture('before installation',['icons'])
        p=self.launcher();before=p.read_bytes()
        with patch.object(self.m,'vendor_launcher',return_value=None):
            _,warnings=self.m.restore(archive,['icons'])
        self.assertEqual(p.read_bytes(),before)
        self.assertTrue(any('No installed default' in w for w in warnings))

    def test_native_and_flatpak_vencord_restore_only_appearance(self):
        for root in ['.config/Vencord','.var/app/com.discordapp.Discord/config/Vencord']:
            with self.subTest(root=root):
                p=self.write(root+'/settings/settings.json',json.dumps({'enabledThemes':['Editor.theme.css'],
                    'themeLinks':['https://example.invalid/theme.css'],'plugins':{'keep':True},'cloud':{'token':'dummy'}}))
                self.write(root+'/themes/Editor.theme.css','/* fixture */')
                archive,_=self.m.capture(root,['discord'])
                p.write_text(json.dumps({'enabledThemes':[],'plugins':{'other':True},'cloud':{'token':'new-dummy'}}))
                self.m.restore(archive,['discord'])
                result=json.loads(p.read_text())
                self.assertEqual(result['enabledThemes'],['Editor.theme.css'])
                self.assertEqual(result['cloud'],{'token':'new-dummy'})
                self.assertEqual(result['plugins'],{'other':True})
                with zipfile.ZipFile(archive) as z:self.assertNotIn(b'dummy',z.read('manifest.json'))

    def test_invalid_window_class_values_are_rejected(self):
        self.launcher();archive,m=self.m.capture('test',['icons'])
        for value in ['',None,42,'Bad\nExec=injected','Bad\x00Value','x'*257]:
            with self.subTest(value=repr(value)):
                data=copy.deepcopy(m);data['app_window_classes']['org.example.Editor.desktop']=value
                bad=self.home/'invalid.look'
                with zipfile.ZipFile(archive) as src,zipfile.ZipFile(bad,'w') as dst:
                    for info in src.infolist():dst.writestr(info,json.dumps(data) if info.filename=='manifest.json' else src.read(info.filename))
                with self.assertRaisesRegex(ValueError,'window class'):self.m.inspect(bad)

    def test_orphan_window_class_is_rejected(self):
        archive,m=self.m.capture('test',['icons']);m['app_window_classes']={'other.desktop':'Other'}
        bad=self.home/'invalid.look'
        with zipfile.ZipFile(bad,'w') as z:z.writestr('manifest.json',json.dumps(m))
        with self.assertRaisesRegex(ValueError,'no saved app launcher'):self.m.inspect(bad)

if __name__=='__main__':unittest.main()
