# Compatibility audit and implementation plan

25 October 2026. Goal: support more applications and installation layouts while
keeping appearance changes separate from whole application/account backups.

## Measured coverage

The 49-test regression suite passes locally in temporary home directories.
Synthetic fixtures cover an invented editor and native, Flatpak and Snap layouts.
No additional apps were installed or real user profiles switched for these tests.

| Behavior exercised | Result |
| --- | --- |
| Native system, user/system Flatpak and Snap launcher export lookup | Pass with synthetic fixtures |
| Absolute `XDG_DATA_DIRS`, ordered roots, invalid relative roots | Pass; `/usr/local/share` precedence corrected |
| Cross-account icon and explicit window-class restore | Pass; receiving commands retained |
| Localized main icons and separate Desktop Action icons | Pass |
| Null icon assignments, absent apps, newer vendor apps, private launchers | Pass; explicit fallback/skip warnings |
| Desktop shortcut round trips and local icon dependencies | Pass for `~/Desktop` |
| Native and Flatpak Vencord, each within its existing layout | Pass; unrelated settings retained |
| Repeated classic/modern Vencord switches | Pass with selected CSS assets restored |
| Invalid window classes, traversal and symlink escapes | Rejected |
| Failure recovery, optional fields, legacy profiles and migration | Pass for covered fixtures |

Existing tests also exercise Millennium appearance merging, Firefox static-theme
filtering and mocked activation. These results do not certify arbitrary apps,
remote theme versions, Wayland, or KDE/GNOME/XFCE sessions. Ubuntu CI tests backend
portability, not a running Cinnamon desktop.

## Six reproduced gaps

Run `/usr/bin/python3 tests/compatibility_probe.py`. Results are saved in
[`compatibility-results.json`](compatibility-results.json). The script explicitly
reports unsupported scenarios; `--require-all` makes those results fail. They are
not counted as passing regression tests.

| Priority | Observed gap | Proposed implementation | Acceptance test |
| --- | --- | --- | --- |
| P0 | Selected Vencord CSS can be missing; archive validation still accepts it | Preflight resolves selected local themes against bundled or verified installed assets before writes | Delete selected CSS; report the missing dependency and do not claim an exact restore succeeded |
| P0 | Native Discord snapshot applied to a Flatpak-only home writes the unused native path | Store logical app identity separately from donor paths; select a receiving installation explicitly | Native→Flatpak and reverse update the chosen target only, retaining unrelated settings |
| P1 | Nondefault `XDG_CONFIG_HOME` is ignored | Central path resolver for config/data/state/cache roots and logical manifest paths | Custom roots inside/outside home, relative invalid roots, different receiving roots |
| P1 | A localized `Bureau` desktop directory is omitted | Resolve XDG user directories and store a logical desktop root; extend destination validation deliberately | Localized folders, spaces/Unicode, disabled desktop pointing to home, different donor/receiver paths |
| P1 | Firefox automatically chooses a profile; no explicit selector | Enumerate installation/profile pairs and bind restoration to a chosen receiving profile | Native work/personal profiles plus Flatpak/Snap; unselected profiles remain unchanged |
| P2 | Remote CSS imports remain network dependencies | Inventory imports; expose online/offline status; optional permitted vendoring with hashes, bounded fetches and URL rewriting | Nested/cyclic imports, fonts/images, redirects, unavailable hosts and offline restores |

The resolver should follow the [XDG specification](https://specifications.freedesktop.org/basedir/latest/), including absolute paths and directory ordering. This release supports `XDG_DATA_DIRS` vendor lookup; complete custom user-data/config-root support remains future work.

## Additional code-review findings

1. **Separate updating from migration.** `update-installed.sh` still invokes a
   personal Windows 95 migration with named wallpaper/font folders. Add a generic
   atomic applet updater with a code backup, and retain that migration under an
   explicitly named command. Ordinary updates should not rename assets or create
   someone else's preset. Test fresh, repeated and failed updates independently.
2. **Diagnose window and tray identity.** Explicit `StartupWMClass` now travels
   with launchers. A read-only doctor should compare desktop-file ID, X11 class,
   Wayland app ID and resolved icon. Suggest repairs individually; visible window
   titles are not reliable identifiers. Tray/status-notifier icons need separate
   diagnosis. The [desktop-entry specification](https://specifications.freedesktop.org/desktop-entry/latest/recognized-keys.html)
   defines these launcher fields, but X11 class is not a universal application ID.
3. **Process handling.** Replace narrow process-name checks with package identity
   and ancestry detection for Flatpak, Snap and alternative clients. Distinguish
   GUIs from services. Saving while apps run can capture older on-disk settings.
   Plan close/save/reopen explicitly, wait for shutdown, and verify after reopening.
   Use bounded waits and avoid inherited stdout pipes that keep launchers waiting.
4. **Make profile meaning visible.** The Vencord selection label exposes empty
   snapshots. Extend previews to all adapters: theme names, target installation,
   missing assets, online dependencies and restart requirements. Distinguish
   settings restored from a theme visibly rendering correctly.
5. **Version and validate adapters.** Define per-app schemas, constrain archive
   contents and validate app/path/group combinations. Optional window-class and
   desktop-icon fields retain compatibility with format-v1 profiles; broader
   semantic changes need explicit schema migrations.

## Adding applications

Introduce an adapter interface instead of expanding path lists indefinitely:

```text
detect(context) -> installations and selectable profiles
capture(target) -> allowlisted appearance settings and dependencies
plan(snapshot, target) -> writes, warnings, restarts and compatibility
validate(plan) -> missing or unsupported inputs before mutation
apply(plan, transaction) -> atomic writes recorded for rollback
verify(target) -> saved values, process state and optional visual checks
```

Each installation needs a logical app ID, package kind, configuration roots,
version and optional profile. Declare narrow settings allowlists, asset types,
safe process handling and restart requirements. Merge structured settings rather
than copying account profiles containing tokens, plugins or workspace data.

| Candidate | Initial scope | Required variants |
| --- | --- | --- |
| VS Code / VSCodium | Color/icon themes, UI font and supported window options | Native, Flatpak, portable/user-data-dir, multiple profiles; JSONC parsing |
| GTK/Qt applications | Toolkit preferences plus app-specific appearance keys | GTK 3/4, libadwaita, qt5ct/qt6ct, native/sandbox settings |
| Terminal emulators | Color schemes and fonts | GNOME Terminal dconf profile UUIDs, Konsole INI profiles, per-instance overrides |
| Vesktop / other Discord clients | Compatible theme selection and CSS | Separate package IDs, configuration schemas and process names |
| Browsers | Themes and narrowly scoped UI preferences | Multiple profiles, native/Flatpak/Snap, Chromium policies |
| Steam | Millennium themes and appearance options | Native/Flatpak, alternate Steam roots, schema changes between versions |

Recommended sequence: preflight and target mapping; XDG/profile discovery; generic
updater and diagnostics; then one new adapter at a time. Require capture/restore,
unrelated-setting preservation, restart verification and injected-failure rollback
tests before marking an adapter supported.

## Integration testing still needed

Use clean Cinnamon VM sessions for X11/Wayland, native and sandbox packages,
localized folders, custom XDG roots, multiple profiles and app versions. Test
active apps, stale processes, missing fonts, monitor changes, read-only folders,
interrupted writes and offline conditions. Use tiny original fixture themes and
disposable accounts. Compare resolved settings and screenshots: a file's presence
does not prove a theme renders. Other desktops require separate settings/layout
backends; cross-platform file tests alone are insufficient.

## Shared software and personal repairs

The corrected Windows 95 Vencord selection and NordVPN launcher binding are local
data. Personal `.look` snapshots and launcher files stay outside Git. The shared
fixes cover restoration behavior, visible theme selection, explicit window-class
metadata, vendor lookup and regression tests. Re-saving a personal look with this
version includes its explicit window-class mapping. Existing profiles stay readable.
