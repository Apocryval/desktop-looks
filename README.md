# Desktop Looks

Save and switch coordinated appearances on a Linux Cinnamon desktop: themes,
fonts, wallpaper, panel layout, app and folder icons, Firefox, Steam/Millennium,
and Discord/Vencord. Version 1.2.0.

## Run or install

Use Python 3 with PyGObject and GTK 3/Gio typelibs. On Ubuntu/Mint:

```sh
sudo apt install python3-gi gir1.2-gtk-3.0
/usr/bin/python3 desktop-looks@local/looks.py gui
```

For a fresh panel-applet installation, run `./install.sh` and add Desktop Looks
through System Settings → Applets. The repository does not distribute personal
`.look` snapshots; import your own profiles through the manager.

Existing installations can use the source manager above to run the updated code.
The legacy `update-installed.sh` performs a **specific Windows 95 asset migration**;
it is not a general updater. Review `migrate.py` before using it. Running that
module without arguments stages a plan; `--apply` moves assets, rewrites profiles
and updates the applet after creating a backup. A generic updater is proposed in
the [compatibility plan](docs/COMPATIBILITY.md).

## Save and switch

Configure the desktop, choose **Save current look**, and give it a name. To switch,
select a saved look and components, then **Apply selected**. A recovery look is
saved first. Import/Export transfers profiles between accounts.

Close Steam, Discord and Firefox completely before restoring their components.
Reopen the manager after updating its source. Panels and desktop layout may need
a logout/login. Profile rows and the apply dialog display the saved Vencord theme
selection, including an explicit empty-selection message. Changing a theme after
saving does not update that existing snapshot; save a new look to retain it.

## Captured appearance

| Component | Scope |
| --- | --- |
| Cinnamon | GTK/window/icon/cursor themes, fonts, wallpaper, panels, applet/desklet settings and personal assets |
| App icons | Main and localized icons, desktop shortcut icons, explicit `StartupWMClass` mappings |
| Folder icons | Gio metadata in standard home folders and configured tracked folders |
| Firefox | Automatically selected profile's static add-on theme, appearance preferences and chrome assets |
| Steam/Millennium | Theme files, active selection, accent/injection options and Quick CSS |
| Discord/Vencord | Theme files, enabled selection, online links, Quick CSS and selected window options |

Icon restore preserves launcher commands and Desktop Action icons. Known newer
apps fall back to their installed vendor icon when an older snapshot has no
override. Private launchers without a vendor default are kept with a warning.
Vendor lookup covers native system, user/system Flatpak and Snap exports, plus
absolute `XDG_DATA_DIRS` locations in preference order.

`StartupWMClass` supports X11 window matching. Saved explicit mappings travel
across accounts; older profiles preserve the receiving launcher's mapping. This
does not implement Wayland app-ID matching or fix tray icons supplied by apps.

Native and Flatpak Vencord paths work separately; automatic translation between
installations is unsupported. Online CSS imports remain online dependencies.
See [tested support and six reproduced gaps](docs/COMPATIBILITY.md).

## Recovery and scope

Profiles live in `~/.local/share/desktop-looks`; the installed applet lives in
`~/.local/share/cinnamon/applets/desktop-looks@local`. Supported app settings are
merged while retaining unrelated values. Application login data, browser history,
games and saves are outside the appearance patches.

Home paths in assets are remapped across accounts. Receiving machines still need
the corresponding applications. Profiles can contain personal paths and executable
applet code; import trusted profiles. Unrelated installed themes are retained.

## Verification

```sh
/usr/bin/python3 -m unittest discover -s tests -v
/usr/bin/python3 tests/compatibility_probe.py
node --check desktop-looks@local/applet.js
sh -n install.sh update-installed.sh
```

49 regression tests pass in disposable homes. Six separate probes reproduce
known unsupported cases; those are not counted as passing support tests.
`compatibility_probe.py --require-all` fails until those gaps are implemented.
GitHub Actions is configured for Ubuntu 22.04 and 24.04.

These are backend/fixture checks, not live certification of every app or desktop.
Live Firefox activation, remote CSS compatibility and Wayland behavior need
separate integration validation.
