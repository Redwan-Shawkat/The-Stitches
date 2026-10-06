"""MySQL's and PostgreSQL's part of their App Manager details: the service
(state, restart), and the users and databases, each with what can be done to
it. Listing and every change ask for the password (pkexec); checking a
password doesn't, it just signs in as that user. Each change shows its
statements (passwords hidden) in the Terminal and is checked against the
listing that comes back with it. It borrows the App Manager page's action
bar and Terminal, as PHP's panel does."""

from gi.repository import Gtk, Pango

from .. import databases as db
from ..shell import tail
from ..widgets import card, confirm, esc, info, label, scrolled, strong

_STATE = {  # systemd ActiveState -> (shown, Pango attributes)
    "active": ("● Running", 'foreground="#1e8a4c" weight="600"'),
    "inactive": ("● Stopped", 'foreground="#c62f28" weight="600"'),
    "failed": ("● Failed", 'foreground="#c62f28" weight="600"'),
    "activating": ("● Starting", 'foreground="#d99a00" weight="600"'),
    "deactivating": ("● Stopping", 'foreground="#d99a00" weight="600"'),
}
_DISMISSED = ("Request dismissed", "Not authorized", "authentication failed", "Error executing command")


def _form(parent, title, action, fields, validate, note=""):
    """A small dialog of `fields` [(key, label, kind)], kind "text",
    "password", "check" or a list of choices. Stays open, saying why, until
    validate(values) is "" or it's cancelled. Values, or None."""
    dialog = Gtk.Dialog(title=title, transient_for=parent, modal=True)
    dialog.add_buttons("Cancel", Gtk.ResponseType.CANCEL, action, Gtk.ResponseType.OK)
    dialog.set_default_response(Gtk.ResponseType.OK)
    grid = Gtk.Grid(column_spacing=12, row_spacing=8, margin=12)
    widgets = {}
    for row, (key, text, kind) in enumerate(fields):
        if kind == "check":
            widgets[key] = Gtk.CheckButton(label=text, active=True)
            grid.attach(widgets[key], 1, row, 1, 1)
            continue
        grid.attach(label(text), 0, row, 1, 1)
        if isinstance(kind, list):
            widgets[key] = Gtk.ComboBoxText()
            for choice in kind:
                widgets[key].append(choice, choice)
            widgets[key].set_active(0)
        else:
            widgets[key] = Gtk.Entry(visibility=kind != "password", activates_default=True, width_chars=28,
                                     input_purpose=Gtk.InputPurpose.PASSWORD if kind == "password" else
                                     Gtk.InputPurpose.FREE_FORM)
        grid.attach(widgets[key], 1, row, 1, 1)
    error = label("", wrap=True, max_width_chars=44)
    error.get_style_context().add_class("error")
    if note:
        grid.attach(label(note, "dim", wrap=True, max_width_chars=44), 0, len(fields), 2, 1)
    grid.attach(error, 0, len(fields) + 1, 2, 1)
    dialog.get_content_area().add(grid)
    dialog.show_all()
    values = None
    while dialog.run() == Gtk.ResponseType.OK:
        got = {k: w.get_active() if isinstance(w, Gtk.CheckButton) else
               w.get_active_id() if isinstance(w, Gtk.ComboBoxText) else w.get_text() for k, w in widgets.items()}
        why = validate(got)
        if not why:
            values = got
            break
        error.set_text(why)
    dialog.destroy()
    return values


def _new_password(v):
    return db.valid_password(v["password"], v["again"])


class DatabasePanel(Gtk.Box):
    def __init__(self, page, engine):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.page, self.engine, self.server, self.listing, self.clusters = page, engine, None, None, []

        top = Gtk.Box(spacing=12, margin=8)
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        info_box.pack_start(label("Server", "card-title"), False, False, 0)
        self.state = label("", use_markup=True)
        info_box.pack_start(self.state, False, False, 0)
        self.signs_in = label("", "dim", wrap=True)
        info_box.pack_start(self.signs_in, False, False, 0)
        top.pack_start(info_box, True, True, 0)
        self.picker = Gtk.ComboBoxText(no_show_all=True, valign=Gtk.Align.CENTER,
                                       tooltip_text="More than one PostgreSQL is installed: the one to manage")
        self.picker_handler = self.picker.connect("changed", self._on_pick)
        top.pack_start(self.picker, False, False, 0)
        self.restart_button = Gtk.Button(valign=Gtk.Align.CENTER)
        self.restart_button.connect("clicked", lambda _b: self._restart())
        top.pack_start(self.restart_button, False, False, 0)
        self.load_button = Gtk.Button(label="Show users and databases", valign=Gtk.Align.CENTER)
        self.load_button.get_style_context().add_class("suggested-action")
        self.load_button.connect("clicked", lambda _b: self._change("Reading users and databases", [], None))
        top.pack_start(self.load_button, False, False, 0)
        self.pack_start(card(top), False, False, 0)

        lists = Gtk.Box(spacing=16, homogeneous=True)
        self.users, self.create_user_button = self._list_card(lists, "Users", "Create user", self._create_user)
        self.databases, self.create_db_button = self._list_card(lists, "Databases", "Create database",
                                                                self._create_database)
        self.pack_start(lists, True, True, 0)

    def _list_card(self, parent, title, action, callback):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=8)
        heading = Gtk.Box(spacing=8)
        heading.pack_start(label(title, "card-title"), True, True, 0)
        button = Gtk.Button(label=action)
        button.connect("clicked", lambda _b: callback())
        heading.pack_start(button, False, False, 0)
        box.pack_start(heading, False, False, 0)
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.pack_start(scrolled(rows), True, True, 0)
        parent.pack_start(card(box), True, True, 0)
        return rows, button

    # ---- the server ----

    def reload(self):
        """The service and how it signs in: no password needed for these."""
        self.page.set_busy(True)
        self.page.run_async(self._read, self._on_read)

    def forget(self):
        """Leaving the details: MySQL's root password, if one was typed, goes."""
        if isinstance(self.server, db.MySQL):
            self.server.root_password = None
        self.listing = None

    def _read(self):
        if self.engine == db.POSTGRES:
            clusters = db.pg_clusters()
            chosen = self.server.cluster if isinstance(self.server, db.Postgres) else None
            keep = next((c for c in clusters if chosen and (c.version, c.name) == (chosen.version, chosen.name)), None)
            cluster = keep or next((c for c in clusters if c.online), clusters[0] if clusters else None)
            same = isinstance(self.server, db.Postgres) and cluster and self.server.cluster.port == cluster.port
            server = self.server if same else db.Postgres(cluster) if cluster else None
            if same:
                server.cluster = cluster  # online or not, as it is now
            return clusters, server, server.service() if server else ("", "")
        server = self.server or db.MySQL()
        return [], server, server.service()

    def _on_read(self, result):
        self.clusters, server, (unit, state) = result
        if server is not self.server:
            self.server, self.listing = server, None
        self.page.set_busy(False)
        self.unit = unit
        with self.picker.handler_block(self.picker_handler):
            self.picker.remove_all()
            for c in self.clusters:
                self.picker.append(f"{c.version}-{c.name}", f"PostgreSQL {c.version} ({c.name}, port {c.port})")
            if isinstance(self.server, db.Postgres):
                self.picker.set_active_id(f"{self.server.cluster.version}-{self.server.cluster.name}")
        self.picker.set_visible(len(self.clusters) > 1)
        if not unit:
            self.state.set_markup(f"{self.engine}'s server isn't installed yet. Install it, and its users and "
                                  "databases show up here.")
            self.signs_in.set_text("")
        else:
            text, attrs = _STATE.get(state, (f"● {state or 'Unknown'}", 'alpha="60%"'))
            self.state.set_markup(f"<span {attrs}>{text}</span>  <span alpha='60%'>{esc(unit)}</span>")
            self.signs_in.set_text(f"Signs in {self.server.signs_in}.")
        self.restart_button.set_label("Restart" if state == "active" else "Start")
        self.restart_button.set_sensitive(bool(unit))
        running = state == "active"
        self.load_button.set_sensitive(running)
        self._show_listing()
        if unit and not running:
            self.page.bar.say(f"{self.engine} isn't running: Start it, then Show users and databases.")
        elif unit:
            self.page.bar.say("Show users and databases asks for your password, then each change asks again.")

    def _on_pick(self, combo):
        version, _, name = (combo.get_active_id() or "").partition("-")
        cluster = next((c for c in self.clusters if (c.version, c.name) == (version, name)), None)
        if cluster:
            self.server, self.listing = db.Postgres(cluster), None
            self.reload()

    def _restart(self):
        verb = self.restart_button.get_label()
        if not confirm(self.page.window(), f"{verb} {self.engine}?",
                       [f"systemctl {verb.lower()} {self.unit}", "",
                        "Anything connected to it (an app, a terminal) loses its connection for a moment."], verb):
            return
        page = self.page
        page.set_busy(True)
        page.bar.pulse()
        page.bar.say(f"{verb}ing {strong(self.unit)} · asks for your password")
        page.terminal.clear()

        def work():
            page.terminal.log(f"▶ {verb} {self.unit}")
            page.terminal.log(f"$ pkexec systemctl {verb.lower()} {self.unit}")
            _ok, text = db.restart(self.unit)
            if text:
                page.terminal.log(text)
            return self._read(), text

        page.run_async(work, self._on_restarted)

    def _on_restarted(self, result):
        read, text = result
        self.page.bar.done()
        self._on_read(read)
        if read[2][1] == "active":
            self.page.bar.say(f"Done: {esc(self.unit)} is running.")
        else:
            self.page.bar.say(f"{esc(self.unit)} isn't running: {esc(tail(text, 1)) or 'see the Terminal'}")

    # ---- the lists ----

    def _show_listing(self):
        for box in (self.users, self.databases):
            for child in box.get_children():
                child.destroy()
        loaded = self.listing is not None
        self.create_user_button.set_sensitive(loaded)
        self.create_db_button.set_sensitive(loaded)
        if not loaded:
            self.users.pack_start(label("Show users and databases lists them here.", "dim", wrap=True), False, False, 0)
        else:
            system_users, system_dbs = db.SYSTEM_USERS[self.engine], db.SYSTEM_DATABASES[self.engine]
            for u in self.listing.users:
                detail = " · ".join(filter(None, [u.host and f"@{u.host}", u.note]))
                mine = u.name not in system_users
                self.users.pack_start(self._row(u.name, detail, [
                    *([("Check password", lambda u=u: self._check_password(u))]
                      if mine or u.name in ("root", "postgres") else []),  # the rest are locked: no sign-in
                    *([("Change password", lambda u=u: self._change_password(u)),
                       ("Delete", lambda u=u: self._delete_user(u))] if mine else [])]), False, False, 0)
            for d in self.listing.databases:
                owner = (f"owner {d.owner}" if self.engine == db.POSTGRES else f"for {d.owner}") if d.owner else ""
                actions = [] if d.name in system_dbs else [("Delete", lambda d=d: self._delete_database(d))]
                self.databases.pack_start(self._row(d.name, owner, actions), False, False, 0)
        self.users.show_all()
        self.databases.show_all()

    def _row(self, name, detail, actions):
        row = Gtk.Box(spacing=6, margin_top=2, margin_bottom=2, height_request=34)  # with buttons or without
        row.pack_start(label(f"<b>{esc(name)}</b>" + (f"  <span alpha='60%'>{esc(detail)}</span>" if detail else ""),
                             use_markup=True, ellipsize=Pango.EllipsizeMode.END, tooltip_text=name), True, True, 0)
        for text, callback in actions:
            button = Gtk.Button(label=text, relief=Gtk.ReliefStyle.NONE)
            if text == "Delete":
                button.get_style_context().add_class("destructive-action")
            button.connect("clicked", lambda _b, c=callback: c())
            row.pack_start(button, False, False, 0)
        return row

    def _user_names(self):
        return [u.name for u in self.listing.users]

    # ---- changes ----

    def _create_user(self):
        mysql = self.engine == db.MYSQL
        v = _form(self.page.window(), f"Create a {self.engine} user", "Create user",
                  [("name", "Name", "text"), ("password", "Password", "password"), ("again", "Again", "password"),
                   ("with_db", "Create a database with the same name, theirs", "check")],
                  lambda v: db.valid_name(v["name"]) or
                  ("There's a user by that name already." if v["name"] in self._user_names() else "") or
                  ("There's a database by that name already." if v["with_db"] and self.listing.database(v["name"])
                   else "") or _new_password(v),
                  note="It signs in from this computer (localhost)." if mysql else "")
        if not v:
            return
        n, pw = v["name"], v["password"]
        sql = db.my_create_user(n, pw, v["with_db"]) if mysql else db.pg_create_user(n, pw, v["with_db"])
        self._change(f"Creating user {n}", sql,
                     lambda l: l.user(n) is not None and (not v["with_db"] or l.database(n) is not None),
                     lambda: self.server.check_password(n, "localhost", pw))

    def _change_password(self, u):
        v = _form(self.page.window(), f"New password for {u.name}", "Change password",
                  [("password", "New password", "password"), ("again", "Again", "password")], _new_password)
        if not v:
            return
        pw = v["password"]
        sql = db.my_password(u.name, u.host, pw) if self.engine == db.MYSQL else db.pg_password(u.name, pw)
        self._change(f"Changing {u.name}'s password", sql, lambda l: l.user(u.name, u.host) is not None,
                     lambda: self.server.check_password(u.name, u.host, pw))

    def _check_password(self, u):
        v = _form(self.page.window(), f"Check {u.name}'s password", "Check",
                  [("password", "Password", "password")], lambda v: "" if v["password"] else "Type the password.",
                  note="Signs in as them with it, then signs out. Nothing changes, and no system password is asked.")
        if not v:
            return
        self.page.set_busy(True)
        self.page.run_async(lambda: self.server.check_password(u.name, u.host, v["password"]),
                            lambda r: self._on_checked(u, r))

    def _on_checked(self, u, result):
        self.page.set_busy(False)
        works, why = result
        if works:
            self.page.bar.say(f"Right: {strong(u.name)} signs in with that password.")
        elif works is False:
            self.page.bar.say(f"Wrong: {strong(u.name)} doesn't sign in with that password.")
        else:
            self.page.bar.say(f"Couldn't check {strong(u.name)}'s password.")
            info(self.page.window(), "Couldn't check it", tail(why, 4))

    def _delete_user(self, u):
        lines = ([f"DROP USER {u.name}@{u.host}", "", "Its databases stay; only the user and what it's allowed "
                  "to do go."] if self.engine == db.MYSQL else
                 [f"DROP ROLE {u.name}", "", "PostgreSQL refuses while it owns a database: delete those first."])
        if not confirm(self.page.window(), f"Delete user {u.name}?", lines, "Delete"):
            return
        sql = db.my_drop_user(u.name, u.host) if self.engine == db.MYSQL else db.pg_drop_user(u.name)
        self._change(f"Deleting user {u.name}", sql, lambda l: l.user(u.name, u.host) is None)

    def _create_database(self):
        mysql = self.engine == db.MYSQL
        owners = [u.name for u in self.listing.users if not mysql or u.name not in db.SYSTEM_USERS[db.MYSQL]]
        owners = (["No one yet", *owners] if mysql else sorted(owners, key=lambda n: n != "postgres"))
        v = _form(self.page.window(), f"Create a {self.engine} database", "Create database",
                  [("name", "Name", "text"), ("owner", "For user" if mysql else "Owner", owners)],
                  lambda v: db.valid_name(v["name"]) or
                  ("There's a database by that name already." if self.listing.database(v["name"]) else ""),
                  note="The user gets every privilege on it." if mysql else "")
        if not v:
            return
        n, owner = v["name"], v["owner"]
        if mysql:
            host = next((u.host for u in self.listing.users if u.name == owner), "localhost")
            sql = db.my_create_database(n, "" if owner == "No one yet" else owner, host)
        else:
            sql = db.pg_create_database(n, owner)
        self._change(f"Creating database {n}", sql, lambda l: l.database(n) is not None)

    def _delete_database(self, d):
        if not confirm(self.page.window(), f"Delete database {d.name}?",
                       [f"DROP DATABASE {d.name}", "", "Every table and row in it is deleted. This can't be undone."],
                       "Delete", critical_ack=f"I understand everything in {d.name} is deleted"):
            return
        sql = db.my_drop_database(d.name) if self.engine == db.MYSQL else db.pg_drop_database(d.name)
        self._change(f"Deleting database {d.name}", sql, lambda l: l.database(d.name) is None)

    def _change(self, heading, statements, took, sign_in=None):
        """The statements, then the listing, in one password prompt; whether it
        took is read from that listing (and, for a password, by signing in)."""
        page = self.page
        page.set_busy(True)
        page.bar.pulse()
        page.bar.say(f"{heading} · asks for your password" if self.server.sudo and not getattr(
            self.server, "root_password", None) else heading)
        page.terminal.clear()

        def work():
            page.terminal.log(f"▶ {self.engine}: {heading}")
            for line in statements:
                page.terminal.log(f"$ {db.shown(line)}")
            ok, listing, err = self.server.run(statements)
            if err:
                page.terminal.log(db.shown(err))
            done = ok and listing is not None and (took is None or took(listing))
            return ok, listing, err, done, sign_in() if done and sign_in else None

        page.run_async(work, lambda r: self._on_changed(r, heading, statements, took, sign_in))

    def _on_changed(self, result, heading, statements, took, sign_in):
        ok, listing, err, done, signed_in = result
        page = self.page
        page.bar.done()
        page.set_busy(False)
        if not ok and isinstance(self.server, db.MySQL) and self.server.needs_root_password(err):
            if self._ask_root_password():
                self._change(heading, statements, took, sign_in)
            else:
                page.bar.say("MySQL's root needs its password here; nothing was changed.")
            return
        if listing is not None:
            self.listing = listing
            self._show_listing()
        if not ok and any(s in err for s in _DISMISSED):
            page.bar.say("Cancelled: no password was given, so nothing ran.")
        elif not done:
            first = next((line for line in err.splitlines() if "ERROR" in line), tail(err, 1))
            page.bar.say(f"{esc(heading)} didn't work: {esc(db.shown(first)) or 'see the Terminal'}")
            info(page.window(), f"{heading} didn't work", tail(db.shown(err), 4) or "It isn't in the list afterwards.")
        elif not statements:
            n, m = len(listing.users), len(listing.databases)
            page.bar.say(f"{n} user{'s' * (n != 1)}, {m} database{'s' * (m != 1)}.")
        elif signed_in is None or signed_in[0]:
            page.bar.say(f"Done: {esc(heading.lower())}" + (", and it signs in with that password." if signed_in
                                                              else "."))
        elif signed_in[0] is False:
            page.bar.say(f"{esc(heading)}: done, but signing in with that password fails.")
        else:
            page.bar.say(f"Done: {esc(heading.lower())}. Couldn't test signing in: {esc(tail(signed_in[1], 1))}")

    def _ask_root_password(self):
        v = _form(self.page.window(), "MySQL's root password", "Sign in",
                  [("password", "Root password", "password")], lambda v: "" if v["password"] else "Type it.",
                  note="This MySQL doesn't let the system's root in through its socket, so it needs root's "
                       "MySQL password. It's kept in memory until you leave these details, never saved.")
        if v:
            self.server.root_password = v["password"]
            self.signs_in.set_text(f"Signs in {self.server.signs_in}.")
        return bool(v)
