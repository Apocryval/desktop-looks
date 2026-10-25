import importlib.util,json,pathlib,sys,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'desktop-looks@local'))
s=importlib.util.spec_from_file_location('migration',ROOT/'migrate.py');M=importlib.util.module_from_spec(s);s.loader.exec_module(M)
class Settings:
 def capture(self):return {'org.cinnamon.theme':{'name':"'Chicago95'"},'org.cinnamon':{'enabled-desklets':"['clock@test:1:100:200']",'lock-desklets':'true'}}
 def apply(self,values,remap):return []
class Desktop:
 def __init__(self,home,fail=False):self.value=repr('file://'+str(home/'Downloads'/M.WALLS[0]));self.fail=fail
 def wallpaper(self):return self.value
 def set_wallpaper(self,value):
  if self.fail and '/Wallpapers/' in value:raise RuntimeError('test wallpaper failure')
  self.value=value
 def sounds(self):return 'unchanged sounds'
 def refresh_fonts(self,home):pass
class MigrationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name);self.home=self.root/'home';self.home.mkdir();self.settings=Settings()
  def write(rel,data):
   p=self.home/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data if isinstance(data,bytes) else data.encode())
  self.write=write
  write('Pictures/App Icons/test.png',b'ICON')
  write('.fonts/vga_font/font.ttf',b'FONT');write('.fonts/vga_font/.uuid','font-cache-marker')
  for name in M.WALLS:write('Downloads/'+name,b'WALLPAPER')
  write('.local/share/applications/test.desktop','[Desktop Entry]\nName=Test\nExec=unchanged\nIcon='+str(self.home)+'/Pictures/App Icons/test.png\nIcon[en_GB]='+str(self.home)+'/Pictures/App Icons/test.png\n')
  write('.local/share/cinnamon/applets/desktop-looks@local/looks.py','OLD HELPER')
  manager=M.looks.Looks(self.home,self.home/'.local/share/desktop-looks',settings=self.settings,metadata=False);manager.running_apps=lambda g:[];self.old,manifest=manager.capture('Old 95')
 def tearDown(self):self.temp.cleanup()
 def test_complete_migration(self):
  desktop=Desktop(self.home);plan=M.apply(self.home,self.root/'stage',self.settings,desktop)
  self.assertTrue(plan['apply_completed']);self.assertTrue(pathlib.Path(plan['backup']).exists())
  self.assertFalse((self.home/'Pictures/App Icons/test.png').exists());self.assertEqual((self.home/M.ICON_NEW/'test.png').read_bytes(),b'ICON')
  self.assertEqual((self.home/'.local/share/fonts/vga_font/font.ttf').read_bytes(),b'FONT')
  content=(self.home/'.local/share/applications/test.desktop').read_text();self.assertIn('Icon[en_GB]='+str(self.home)+'/'+M.ICON_NEW+'test.png',content);self.assertIn('Exec=unchanged',content)
  self.assertIn('/Pictures/Wallpapers/Windows95/',desktop.wallpaper());self.assertTrue((self.home/'.local/share/cinnamon/applets/desktop-looks@local/firefox_looks.py').exists())
  import zipfile
  with zipfile.ZipFile(self.old) as z:
   m=json.loads(z.read('manifest.json'));self.assertIn(M.ICON_NEW+'test.png',[f['path'] for f in m['files']]);self.assertNotIn(str(self.home)+'/Pictures/App Icons/',json.dumps(m))
 def test_migration_rolls_back_on_failure(self):
  desktop=Desktop(self.home,fail=True)
  with self.assertRaisesRegex(RuntimeError,'wallpaper failure'):M.apply(self.home,self.root/'stage',self.settings,desktop)
  self.assertEqual((self.home/'Pictures/App Icons/test.png').read_bytes(),b'ICON');self.assertTrue((self.home/'Downloads'/M.WALLS[0]).exists());self.assertTrue((self.home/'.fonts/vga_font/font.ttf').exists());self.assertEqual((self.home/'.local/share/cinnamon/applets/desktop-looks@local/looks.py').read_text(),'OLD HELPER');self.assertFalse((self.home/'.local/share/cinnamon/applets/desktop-looks@local/firefox_looks.py').exists())
if __name__=='__main__':unittest.main(verbosity=2)
