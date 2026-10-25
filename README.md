# Desktop Looks 1.1

Save coordinated desktop appearances: themes, fonts, cursors, wallpaper, panel/menu choices, desklets, custom icons, Firefox, Millennium and Vencord.

## Update your existing installation

Extract Desktop-Looks-v1.1.zip and run update-installed.sh from your normal desktop. This performs the approved asset migration and updates your installed applet. You already approved these changes; the script is executable and needs no administrator privileges.

The updater creates a complete backup before moving assets. It moves the two Windows 95 wallpapers from Downloads into Pictures/Wallpapers/Windows95, custom app icon images from Pictures/App Icons into .local/share/icons/custom-apps/windows95, and the three personal font directories into .local/share/fonts. It keeps the icon prompts text with the source material, preserves the image/font contents, updates every launcher icon variant and the active wallpaper path, migrates all saved looks it finds, and adds a fresh current look with Firefox and desktop layout. Sounds stay unchanged.

If migration fails, the updater attempts rollback from its backup and move journal. To prepare/review without applying, run /usr/bin/python3 migrate.py. The staged plan is written into Migration-stage/plan.json. A completed migration records apply_completed=true and the backup path there.

This update has been PREPARED BUT NOT APPLIED by the agent. Individual-file access grants broke the normal command runner, and the alternative file tools still see live folders as read-only. The installed v1.0 applet and live assets remain unchanged by this task. Running the updater from your normal desktop bypasses that execution-environment problem through your own user session. Alternatively, ask the agent to continue in a fresh turn with directory-level access only.

## Fresh installation

Run install.sh, then add Desktop Looks through System Settings → Applets. If an installation already exists, use update-installed.sh instead. The installer imports the included Current-95-Firefox.look; importing does not apply the look automatically.

You can use the manager without installing the panel applet by running /usr/bin/python3 desktop-looks@local/looks.py gui.

## Everyday workflow

Configure your desktop normally, then Save current look under a memorable name. To switch, select a saved look, choose the components, and Apply selected. A recovery look is saved first. Import and Export move personal look files between accounts.

Close Steam, Discord and Firefox completely before applying their selected appearance components. Log out and back in after restoring panels, applets, desklets or desktop icon placement.

## Fonts and desktop layout

A look includes selected interface/document/monospace/title fonts, text scaling, personal font files, theme/icon/cursor assets, window styling, wallpaper, panel position/height/hiding delays, applet selection and placement, Classic Menu settings, enabled extensions and their settings.

Desklets include enabled selection, X/Y coordinates, decoration, snapping/grid size, locking, and personal settings/assets. The enabled-desklet list stores the coordinates. Your current desklet list is empty. Nemo desktop icon placement is captured from .config/nemo/desktop-metadata. Position coordinates are restored as saved; a changed monitor arrangement may require repositioning.

Custom app icon assignment restores base and localized Icon fields without changing the receiving launcher's Exec command. Personal folder-icon metadata is scanned in standard home folders and two levels below them. Use Track folder icons to include additional folders within your home. No folder-icon metadata was visible to this execution session; make a fresh save from the normal desktop to capture it there.

## Firefox

The new component saves the default profile's selected static add-on theme and its package, browser appearance/font preferences, toolbar layout, and chrome CSS/images/fonts. It does not copy browsing history, bookmarks, passwords, sessions, unrelated extension settings or the entire browser profile. The receiving account needs an existing Firefox profile; start Firefox once if necessary.

Theme activation is delegated to Firefox's own AddonManager in a brief offline headless session while Firefox is closed. The adapter restores its temporary startup settings and saved browser-session files afterwards; it does not hand-edit the add-on database. The current snapshot uses Windows 95. Any custom CSS remains subject to Firefox version changes.

Firefox capture, selective preference restoration, static-theme validation and automation protocol framing are tested. Live theme activation could NOT be tested here: Firefox crashes or cannot open local sockets in this execution environment. Verify the activation adapter from the normal desktop before relying on browser theme switching. Other tested components do not depend on that Firefox activation check.

## Steam and Discord

Millennium captures theme files, active selection, theme conditions, accent/injection choices and Quick CSS. Vencord captures themes, enabled selections, online theme links, Quick CSS and selected window appearance options, including Flatpak Discord. Their other settings and login data are not part of the appearance patches. Online CSS imports remain online imports rather than frozen copies of remote sites.

## Recovery, privacy and storage

Saved looks live in .local/share/desktop-looks. The applet lives in .local/share/cinnamon/applets/desktop-looks@local. Each look/recovery is independent; delete unwanted old profiles through Open saved looks. Profiles can contain personal paths, wallpaper images and applet preferences, and saved applets/extensions can contain code: import trusted looks and review before sharing publicly.

Personal home paths in saved settings and text assets are remapped when importing to another user. System applications must be installed separately. Games, game saves and Steam library permissions are not managed. System-wide theme modifications are not copied. Theme assets are restored without removing unrelated installed theme folders.

## Verification

24 tests passed: 22 backend/Firefox/layout tests, plus complete migration and rollback tests in temporary home folders. All six current saved looks were staged and validated without changing their live originals. A new current snapshot includes 36,926 asset/configuration entries, 72 desktop settings, 21 app icon assignments and Firefox. The applet's JavaScript passes syntax checking. Live Firefox activation remains unverified as explained above.
