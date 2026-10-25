import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop-looks@local'))
import looks as L


class DiscordTests(unittest.TestCase):
    def test_flatpak_theme_selection_survives_repeated_switches(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)
            settings=home/'.var/app/com.discordapp.Discord/config/Vencord/settings/settings.json'
            settings.parent.mkdir(parents=True)
            themes=settings.parent.parent/'themes'
            themes.mkdir()
            for name in ['WinClassic.theme.css','cyberpunk2077.theme.css']:
                (themes/name).write_text('/* '+name+' */')
            manager=L.Looks(home,metadata=False)
            manager.running_apps=lambda groups:[]
            archives=[]
            for name in ['WinClassic.theme.css','cyberpunk2077.theme.css']:
                settings.write_text(json.dumps({'enabledThemes':[name],'themeLinks':[],
                    'useQuickCss':True,'plugins':{'unchanged':True},'unrelated':'keep-me'}))
                archive,m=manager.capture(name,['discord'])
                self.assertIn(name,L.discord_theme_summary(m))
                archives.append((archive,name))
            for archive,name in archives*2:
                manager.restore(archive,['discord'])
                d=json.loads(settings.read_text())
                self.assertEqual(d['enabledThemes'],[name])
                self.assertEqual(d['plugins'],{'unchanged':True})
                self.assertEqual(d['unrelated'],'keep-me')
                self.assertTrue((themes/name).is_file())

    def test_summary_makes_empty_selection_visible(self):
        m={'groups':['discord'],'json_patches':[{'group':'discord','values':{'enabledThemes':[]}}]}
        self.assertEqual(L.discord_theme_summary(m),'Discord theme: no theme selected')

    def test_summary_distinguishes_missing_settings_and_unselected_component(self):
        self.assertEqual(L.discord_theme_summary({'groups':['discord']}),'Discord theme: no saved Vencord settings')
        self.assertEqual(L.discord_theme_summary({'groups':['desktop']}),'')

if __name__=='__main__':unittest.main()
