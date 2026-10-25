import importlib.util, json, pathlib, tempfile, unittest, zipfile, sys, copy
module=pathlib.Path(__file__).resolve().parents[1]/'desktop-looks@local'/'looks.py'
sys.path.insert(0,str(module.parent));spec=importlib.util.spec_from_file_location('looks',module);L=importlib.util.module_from_spec(spec);spec.loader.exec_module(L)
class FakeSettings:
 def __init__(self):self.data={'org.cinnamon.theme':{'name':"'Chicago95'"},'org.cinnamon':{'enabled-applets':"['1:left:0:classic-menu@fredcw:15']"},'org.cinnamon.desktop.background':{'picture-uri':"'file:///home/old/Pictures/wall.png'"}}
 def capture(self):return copy.deepcopy(self.data)
 def apply(self,data,remap):self.data={k:{a:remap(v) for a,v in values.items()} for k,values in data.items()};return []
class Tests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name);self.home=self.root/'old';self.home.mkdir();self.backend=FakeSettings();self.backend.data['org.cinnamon.desktop.background']['picture-uri']=repr('file://'+str(self.home)+'/Pictures/wall.png')
  self.m=L.Looks(self.home,self.root/'store',self.backend,metadata=False)
  self.write('.themes/Chicago95/gtk-4.0/gtk.css','/* original */')
  self.write('.config/gtk-4.0/gtk.css','@import url("file://'+str(self.home)+'/.themes/Chicago95/gtk-4.0/gtk.css");')
  self.write('.config/cinnamon/spices/classic-menu@fredcw/15.json','{"menu-icon":{"value":"gnome-main-menu"}}')
  self.write('Pictures/App Icons/gpt95.png',b'PNG')
  self.write('Pictures/wall.png',b'WALL')
  self.write('.local/share/applications/chatgpt.desktop','[Desktop Entry]\nName=ChatGPT\nExec=chatgpt %U\nIcon='+str(self.home)+'/Pictures/App Icons/gpt95.png\n')
  self.write('.config/millennium/config.json',json.dumps({'themes':{'activeTheme':'win95-themes'},'general':{'accentColor':'RED','checkForMillenniumUpdates':True},'network':{'proxyPassword':'SECRET'}}))
  self.write('.var/app/com.discordapp.Discord/config/Vencord/settings/settings.json',json.dumps({'enabledThemes':['WinClassic.theme.css'],'themeLinks':[],'useQuickCss':True,'plugins':{'example':{'enabled':True}},'cloud':{'token':'SECRET'}}))
  self.write('.var/app/com.discordapp.Discord/config/Vencord/themes/WinClassic.theme.css','/* local theme */')
  self.write('.var/app/com.discordapp.Discord/config/Vencord/settings/quickCss.css','/* custom css */')
  self.m.running_apps=lambda groups:[]
 def tearDown(self):self.temp.cleanup()
 def write(self,rel,data):
  p=self.home/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data if isinstance(data,bytes) else data.encode());return p
 def capture(self):return self.m.capture('My classic look')
 def test_capture_contains_assets_and_no_credentials(self):
  p,m=self.capture();self.m.inspect(p)
  self.assertIn('Pictures/App Icons/gpt95.png',[f['path'] for f in m['files']]);self.assertIn('Pictures/wall.png',[f['path'] for f in m['files']])
  self.assertIn('.config/cinnamon/spices/classic-menu@fredcw/15.json',[f['path'] for f in m['files']])
  with zipfile.ZipFile(p) as z:self.assertNotIn(b'SECRET',z.read('manifest.json'))
 def test_restore_keeps_unrelated_application_settings(self):
  p,m=self.capture();self.write('.config/millennium/config.json',json.dumps({'themes':{'activeTheme':'NEW'},'network':{'proxyPassword':'NEWSECRET'},'general':{'accentColor':'BLUE','checkForMillenniumUpdates':False}}))
  rel='.var/app/com.discordapp.Discord/config/Vencord/settings/settings.json';self.write(rel,json.dumps({'enabledThemes':['OTHER'],'cloud':{'token':'NEWSECRET'},'plugins':{'new':{'enabled':True}}}))
  self.write('.config/gtk-4.0/gtk.css','/* changed */')
  recovery,warnings=self.m.restore(p)
  d=json.loads((self.home/'.config/millennium/config.json').read_text());self.assertEqual(d['themes']['activeTheme'],'win95-themes');self.assertEqual(d['network']['proxyPassword'],'NEWSECRET');self.assertFalse(d['general']['checkForMillenniumUpdates'])
  d=json.loads((self.home/rel).read_text());self.assertEqual(d['enabledThemes'],['WinClassic.theme.css']);self.assertEqual(d['cloud']['token'],'NEWSECRET');self.assertTrue(d['plugins']['new']['enabled'])
  self.assertTrue(recovery.exists());self.assertIn('@import',(self.home/'.config/gtk-4.0/gtk.css').read_text());self.assertFalse(warnings)
 def test_cross_account_remaps_paths_and_leaves_exec(self):
  p,m=self.capture();home=self.root/'new';home.mkdir();b=FakeSettings();other=L.Looks(home,self.root/'other-store',b,metadata=False);other.running_apps=lambda groups:[]
  q=home/'.local/share/applications/chatgpt.desktop';q.parent.mkdir(parents=True);q.write_text('[Desktop Entry]\nName=ChatGPT\nExec=changed-launcher --safe\nIcon=old\n')
  other.restore(p)
  self.assertIn(str(home)+'/.themes',(home/'.config/gtk-4.0/gtk.css').read_text());self.assertNotIn(str(self.home),(home/'.config/gtk-4.0/gtk.css').read_text());self.assertIn('Exec=changed-launcher --safe',q.read_text());self.assertIn('Icon='+str(home)+'/Pictures/App Icons/gpt95.png',q.read_text());self.assertTrue((home/'Pictures/App Icons/gpt95.png').exists())
 def test_optional_css_absence_restores_default(self):
  (self.home/'.config/gtk-4.0/gtk.css').unlink();p,m=self.capture();self.write('.config/gtk-4.0/gtk.css','override');self.m.restore(p,['desktop']);self.assertFalse((self.home/'.config/gtk-4.0/gtk.css').exists())
 def test_selective_restore(self):
  p,m=self.capture();self.write('.config/gtk-4.0/gtk.css','NEW CSS');self.m.restore(p,['icons']);self.assertEqual((self.home/'.config/gtk-4.0/gtk.css').read_text(),'NEW CSS')
 def test_running_clients_block_before_writes(self):
  p,m=self.capture();self.m.running_apps=lambda groups:['Steam'];self.write('.config/gtk-4.0/gtk.css','UNCHANGED')
  with self.assertRaisesRegex(RuntimeError,'Close Steam'):self.m.restore(p)
  self.assertEqual((self.home/'.config/gtk-4.0/gtk.css').read_text(),'UNCHANGED')
 def rewrite(self,p,change):
  q=self.root/'altered.look'
  with zipfile.ZipFile(p) as z,zipfile.ZipFile(q,'w') as out:
   m=json.loads(z.read('manifest.json'));change(m)
   for name in z.namelist():
    if name!='manifest.json':out.writestr(name,z.read(name))
   out.writestr('manifest.json',json.dumps(m))
  return q
 def test_path_traversal_rejected_before_restore(self):
  p,m=self.capture();q=self.rewrite(p,lambda m:m['files'].append({'path':'../../outside','group':'desktop','kind':'file'}))
  with self.assertRaises(ValueError):self.m.restore(q)
 def test_unrelated_settings_rejected(self):
  p,m=self.capture();q=self.rewrite(p,lambda m:m['settings'].update({'org.gnome.online-accounts':{'anything':'true'}}))
  with self.assertRaises(ValueError):self.m.inspect(q)
 def test_symlink_escape_rejected(self):
  p,m=self.capture();q=self.rewrite(p,lambda m:m['files'].append({'path':'.themes/bad','group':'desktop','kind':'symlink','target':'/tmp'}))
  with self.assertRaises(ValueError):self.m.inspect(q)
 def test_import_validates_and_copies(self):
  p,m=self.capture();q,manifest=self.m.import_profile(p);self.assertTrue(q.exists());self.assertEqual(manifest['name'],m['name'])
 def test_failure_restores_old_theme_settings(self):
  p,m=self.capture();self.write('.config/gtk-4.0/gtk.css','BEFORE FAILURE');original=self.m._apply;count=[0]
  def fail_once(*args):
   count[0]+=1
   if count[0]==1:
    original(*args);raise RuntimeError('simulated failure')
   return original(*args)
  self.m._apply=fail_once
  with self.assertRaisesRegex(RuntimeError,'previous appearance was restored'):self.m.restore(p)
  self.assertEqual((self.home/'.config/gtk-4.0/gtk.css').read_text(),'BEFORE FAILURE')
 def test_manager_stays_on_existing_panel_without_id_collision(self):
  v=L.preserve_manager("['1:left:0:classic-menu@fredcw:15']","['7:right:0:desktop-looks@local:15']",panels="['1:0:bottom']")
  self.assertEqual(L.variants(v),['1:left:0:classic-menu@fredcw:15','1:right:0:desktop-looks@local:16'])

 def test_folder_icon_restore_and_clear_use_valid_gio_api(self):
  from gi.repository import Gio
  from unittest.mock import patch
  self.write('Documents/placeholder','x');self.write('Pictures/placeholder','x')
  self.m.metadata=True
  self.m.folder_icons=lambda:({'.':{'metadata::custom-icon-name':'user-home'},'Documents':{'metadata::custom-icon-name':'folder-documents'}},[])
  p,m=self.capture()
  self.m.folder_icons=lambda:({'Pictures':{'metadata::custom-icon-name':'folder-pictures'}},[])
  calls=[]
  class FakeFile:
   def __init__(self,path):self.path=path
   def set_attributes_from_info(self,info,flags,cancel):
    calls.append((self.path,info.get_attribute_type('metadata::custom-icon-name'),info.get_attribute_string('metadata::custom-icon-name') if info.get_attribute_type('metadata::custom-icon-name')==Gio.FileAttributeType.STRING else None));return True,info
  with patch.object(Gio.File,'new_for_path',side_effect=lambda p:FakeFile(p)):
   self.m.restore(p,['icons'])
  values={path:(kind,value) for path,kind,value in calls}
  self.assertEqual(values[str(self.home/'Documents')][1],'folder-documents')
  self.assertEqual(values[str(self.home/'Pictures')][0],Gio.FileAttributeType.INVALID)
  self.assertEqual(values[str(self.home)][1],'user-home')

 def test_empty_selection_never_applies_everything(self):
  p,m=self.capture()
  with self.assertRaisesRegex(ValueError,'at least one'):self.m.restore(p,[])
  with self.assertRaisesRegex(ValueError,'at least one'):self.m.capture('empty',[])

 def test_localized_icons_follow_the_saved_icon(self):
  original='[Desktop Entry]\nExec=keep-this\nIcon=old\nIcon[en_GB]=localized-old\n'
  changed=L.change_icon(original,'new')
  self.assertIn('Icon=new',changed);self.assertIn('Icon[en_GB]=new',changed);self.assertIn('Exec=keep-this',changed)
 def test_new_icon_asset_folder_is_saved_with_icons_only(self):
  self.write('.local/share/icons/custom-apps/windows95/gpt.png',b'ICON')
  p,m=self.m.capture('Icons only',['icons'])
  self.assertIn('.local/share/icons/custom-apps/windows95/gpt.png',[f['path'] for f in m['files']])
 def test_desklet_positions_and_desktop_icon_layout(self):
  self.backend.data['org.cinnamon']['enabled-desklets']="['clock@cinnamon.org:3:145:230']"
  self.backend.data['org.cinnamon']['lock-desklets']='true'
  self.write('.config/nemo/desktop-metadata','[test]\nnemo-icon-position=24,48\n')
  p,m=self.capture();self.backend.data['org.cinnamon']['enabled-desklets']='[]';self.write('.config/nemo/desktop-metadata','CHANGED')
  self.m.restore(p,['desktop'])
  self.assertIn('145:230',self.backend.data['org.cinnamon']['enabled-desklets']);self.assertEqual(self.backend.data['org.cinnamon']['lock-desklets'],'true')
  self.assertIn('24,48',(self.home/'.config/nemo/desktop-metadata').read_text())
 def firefox_fixture(self):
  rel='.mozilla/firefox/testing.default';self.write('.mozilla/firefox/profiles.ini','[InstallABC]\nDefault=testing.default\n[Profile0]\nName=default-release\nIsRelative=1\nPath=testing.default\n')
  self.write(rel+'/prefs.js','user_pref("extensions.activeThemeID", "classic@test");\nuser_pref("browser.uidensity", 1);\nuser_pref("private.unrelated", "SECRET");\n')
  self.write(rel+'/user.js','// custom comment\nuser_pref("network.unrelated", true);\n')
  self.write(rel+'/chrome/userChrome.css','/* custom chrome */')
  package=self.home/rel/'extensions/classic@test.xpi';package.parent.mkdir(parents=True,exist_ok=True)
  with zipfile.ZipFile(package,'w') as z:z.writestr('manifest.json',json.dumps({'manifest_version':2,'name':'Classic','version':'1','theme':{'colors':{}},'browser_specific_settings':{'gecko':{'id':'classic@test'}}}))
  self.write(rel+'/extensions.json',json.dumps({'addons':[{'type':'theme','id':'classic@test','path':str(package),'active':True,'defaultLocale':{'name':'Classic'}}]}))
  return self.home/rel
 def test_firefox_capture_is_appearance_only(self):
  p=self.firefox_fixture();archive,m=self.capture();self.m.inspect(archive)
  self.assertEqual(m['firefox']['theme_id'],'classic@test');self.assertNotIn('private.unrelated',m['firefox']['preferences'])
  self.assertIn('@firefox/theme.xpi',[f['path'] for f in m['files']])
  self.assertIn('@firefox/chrome/userChrome.css',[f['path'] for f in m['files']])
 def test_firefox_restore_preserves_unrelated_prefs_and_delegates_theme(self):
  from unittest.mock import patch
  p=self.firefox_fixture();archive,m=self.capture()
  self.write(str(p.relative_to(self.home))+'/prefs.js','user_pref("extensions.activeThemeID", "other@test");\nuser_pref("browser.uidensity", 2);\nuser_pref("private.unrelated", "STILLHERE");\n')
  with patch.object(L.firefox,'activate_theme') as activate:self.m.restore(archive,['firefox']);self.assertEqual(activate.call_args.args[1],'classic@test')
  data=L.firefox.parse((p/'prefs.js').read_text());self.assertEqual(data['browser.uidensity'],1);self.assertEqual(data['private.unrelated'],'STILLHERE');self.assertEqual(data['extensions.activeThemeID'],'other@test')
  self.assertIn('custom comment',(p/'user.js').read_text())
 def test_firefox_running_blocks_restore(self):
  self.firefox_fixture();archive,m=self.capture();self.m.running_apps=lambda groups:['Firefox']
  with self.assertRaisesRegex(RuntimeError,'Close Firefox'):self.m.restore(archive,['firefox'])
 def test_firefox_theme_asset_cannot_contain_executable_extension(self):
  p=self.firefox_fixture();package=p/'extensions/classic@test.xpi'
  with zipfile.ZipFile(package,'w') as z:z.writestr('manifest.json',json.dumps({'manifest_version':2,'name':'Bad','version':'1','theme':{},'background':{'scripts':['bad.js']}}))
  archive,m=self.capture()
  with self.assertRaisesRegex(ValueError,'not a static theme'):self.m.inspect(archive)
 def test_marionette_protocol_framing(self):
  def frame(obj):
   data=json.dumps(obj).encode();return str(len(data)).encode()+b':'+data
  class Sock:
   def __init__(self):self.data=frame({'marionetteProtocol':3})+frame([1,1,None,{'ok':True}]);self.sent=b''
   def recv(self,count):value=self.data[:count];self.data=self.data[count:];return value
   def sendall(self,value):self.sent+=value
  sock=Sock();client=L.firefox.Marionette(sock);self.assertEqual(client.call('Test'),{'ok':True});self.assertIn(b'Test',sock.sent)

if __name__=='__main__':unittest.main(verbosity=2)
