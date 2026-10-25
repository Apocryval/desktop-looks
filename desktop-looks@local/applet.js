const Applet = imports.ui.applet;
const PopupMenu = imports.ui.popupMenu;
const Main = imports.ui.main;
const Gio = imports.gi.Gio;
const GLib = imports.gi.GLib;
const Util = imports.misc.util;

class DesktopLooks extends Applet.IconApplet {
    constructor(metadata, orientation, panelHeight, instanceId) {
        super(orientation, panelHeight, instanceId);
        this.path = metadata.path;
        this.set_applet_icon_symbolic_name('preferences-desktop-theme-symbolic');
        this.set_applet_tooltip('Desktop Looks — themes, menus, icons, Steam and Discord');
        this.manager = new PopupMenu.PopupMenuManager(this);
        this.menu = new Applet.AppletPopupMenu(this, orientation);
        this.manager.addMenu(this.menu);
        this._fill();
    }
    _launch() {
        Util.spawn(['/usr/bin/python3', this.path + '/looks.py', 'gui']);
    }
    _fill() {
        this.menu.removeAll();
        const title = new PopupMenu.PopupMenuItem('Desktop Looks', {reactive: false});
        this.menu.addMenuItem(title);
        const manage = new PopupMenu.PopupMenuItem('Save or switch a look…');
        manage.connect('activate', () => this._launch());
        this.menu.addMenuItem(manage);
        const folder = new PopupMenu.PopupMenuItem('Open saved looks');
        folder.connect('activate', () => {
            const path = GLib.build_filenamev([GLib.get_home_dir(), '.local', 'share', 'desktop-looks']);
            GLib.mkdir_with_parents(path, 448);
            Gio.AppInfo.launch_default_for_uri(Gio.File.new_for_path(path).get_uri(), null);
        });
        this.menu.addMenuItem(folder);
        const themes = new PopupMenu.PopupMenuItem('Open standard theme settings');
        themes.connect('activate', () => Util.spawn(['cinnamon-settings', 'themes']));
        this.menu.addMenuItem(themes);
    }
    on_applet_clicked() { this.menu.toggle(); }
    on_applet_removed_from_panel() { this.manager.removeMenu(this.menu); this.menu.destroy(); }
}
function main(metadata, orientation, panelHeight, instanceId) {
    return new DesktopLooks(metadata, orientation, panelHeight, instanceId);
}
