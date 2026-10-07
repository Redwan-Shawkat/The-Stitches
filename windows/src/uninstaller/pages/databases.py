"""MySQL's and PostgreSQL's part of their App Manager details, as on Linux:
the service (state, Start/Restart, a picker when several PostgreSQL versions
are installed), and the users and databases, each with what can be done to
it. Every change shows its statements (passwords hidden) in the Terminal and
is checked against the listing that comes back after it. It borrows the App
Manager page's action bar, Terminal, set_busy and run_async.

The one real difference from Linux: Windows has no peer or socket
authentication, so the server's own superuser password is asked for before
anything can be listed, and it's kept in memory for this visit only."""

import tkinter as tk

from .. import databases as db
from ..elevate import tail
from ..widgets import FONTS, Button, Dialog, Rounded, confirm, info, px, role

_STATE = {  # a Windows service's Status -> (shown, colour)
    "running": ("● Running", "#1e8a4c"),
    "stopped": ("● Stopped", "#c62f28"),
    "paused": ("● Paused", "#d99a00"),
    "startpending": ("● Starting", "#d99a00"),
    "stoppending": ("● Stopping", "#d99a00"),
}
_DISMISSED = ("The operation was canceled by the user", "Access is denied", "cancelled by the user")
_ROWS = 7  # how many rows a list card shows before it scrolls


def _form(parent, title, action, fields, validate, note=""):
    """A small dialog of `fields` [(key, label, kind)], kind "text",
    "password", "check" or a list of choices. Stays open, saying why, until
    validate(values) is "" or it's cancelled. Values, or None."""
    while True:
        dialog = Dialog(parent, title)
        grid = tk.Frame(dialog.body)
        grid.pack(fill="x")
        widgets, variables = {}, {}
        for row, (key, text, kind) in enumerate(fields):
            if kind == "check":
                variables[key] = tk.BooleanVar(value=True)
                tk.Checkbutton(grid, text=text, variable=variables[key], anchor="w", borderwidth=0,
                               highlightthickness=0).grid(row=row, column=1, sticky="w", pady=px(3))
                continue
            role(tk.Label(grid, text=text, anchor="w"), fg="dim").grid(row=row, column=0, sticky="w",
                                                                      padx=(0, px(10)), pady=px(3))
            variables[key] = tk.StringVar()
            if isinstance(kind, list):
                variables[key].set(kind[0] if kind else "")
                widgets[key] = tk.OptionMenu(grid, variables[key], *(kind or [""]))
            else:
                widgets[key] = tk.Entry(grid, textvariable=variables[key], width=30, relief="flat",
                                        show="•" if kind == "password" else "")
            widgets[key].grid(row=row, column=1, sticky="we", pady=px(3))
        if note:
            role(tk.Label(dialog.body, text=note, wraplength=px(360), justify="left", anchor="w"),
                 fg="dim").pack(fill="x", pady=(px(8), 0))
        if _form.why:
            role(tk.Label(dialog.body, text=_form.why, wraplength=px(360), justify="left", anchor="w",
                          foreground="#c62f28"), fixed=True).pack(fill="x", pady=(px(8), 0))
        dialog.button("Cancel")
        dialog.button(action, True, "suggested")
        first = next((w for k, w in widgets.items()), None)
        if first:
            first.focus_set()
        if dialog.run() is not True:
            _form.why = ""
            return None
        got = {k: v.get() for k, v in variables.items()}
        _form.why = validate(got)
        if not _form.why:
            return got


_form.why = ""  # why the last attempt was refused, shown on the next one


def _new_password(v):
    return db.valid_password(v["password"], v["again"])


class DatabasePanel(tk.Frame):
    """Gridded into the App Manager's details under MySQL's and
    PostgreSQL's tiles, and shown only while one of them is open."""

    def __init__(self, parent, page, engine):
        super().__init__(parent)  # laid out in the details; `page` is whose bar and Terminal it borrows
        self.page, self.engine = page, engine
        self.server, self.listing, self.installs, self.service_name = None, None, [], ""
        self.columnconfigure((0, 1), weight=1, uniform="db")
        self.rowconfigure(1, weight=1)

        top = Rounded(self, radius=14, pad=12, bg="card", border="border")
        words = tk.Frame(top.inner)
        words.pack(side="left", fill="x", expand=True)
        role(tk.Label(words, text="SERVER", font=FONTS["caps"], anchor="w"), fg="dim").pack(fill="x")
        self.state = tk.Label(words, anchor="w", font=FONTS["bold"])
        self.state.pack(fill="x")
        self.signs_in = role(tk.Label(words, anchor="w", justify="left", wraplength=px(430)), fg="dim")
        self.signs_in.pack(fill="x")
        self.load_button = Button(top.inner, "Show users and databases", self._load, "suggested")
        self.restart_button = Button(top.inner, "Restart", self._restart)
        self.picked = tk.StringVar()
        self.picker = tk.OptionMenu(top.inner, self.picked, "")
        top.configure(height=px(84))
        top.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, px(10)))

        self.users, self.create_user_button = self._list_card("Users", "Create user", self._create_user, 0)
        self.databases, self.create_db_button = self._list_card("Databases", "Create database",
                                                                self._create_database, 1)

    def _list_card(self, title, action, callback, column):
        card = Rounded(self, radius=14, pad=12, bg="card", border="border")
        heading = tk.Frame(card.inner)
        heading.pack(fill="x")
        role(tk.Label(heading, text=title.upper(), font=FONTS["caps"], anchor="w"), fg="dim").pack(side="left")
        button = Button(heading, action, callback)
        button.pack(side="right")
        rows = tk.Frame(card.inner)
        rows.pack(fill="both", expand=True, pady=(px(6), 0))
        card.configure(height=px(40 + _ROWS * 30))
        card.grid(row=1, column=column, sticky="nsew", padx=((0, px(5)) if column == 0 else (px(5), 0)))
        return rows, button

    # ---- the server ----

    def reload(self):
        """The service and how it signs in: no password needed for these."""
        self.page.set_busy(True)
        self.page.run_async(self._read, self._on_read)

    def forget(self):
        """Leaving the details: the superuser password typed here goes with it."""
        if self.server is not None:
            if isinstance(self.server, db.MySQL):
                self.server.root_password = None
            else:
                self.server.superuser_password = None
        self.listing = None

    def _read(self):
        if self.engine == db.POSTGRES:
            installs = db.pg_installs()
            chosen = self.server.install if isinstance(self.server, db.Postgres) else None
            keep = next((i for i in installs if chosen and i.version == chosen.version), None)
            install = keep or (installs[0] if installs else None)
            same = isinstance(self.server, db.Postgres) and install and self.server.install.version == install.version
            server = self.server if same else db.Postgres(install) if install else None
            return installs, server, server.service() if server else ("", "")
        server = self.server or db.MySQL()
        return [], server, server.service()

    def _on_read(self, result):
        self.installs, server, (service, state) = result
        if server is not self.server:
            self.server, self.listing = server, None
        self.page.set_busy(False)
        self.service_name = service
        self._fill_picker()
        if not service:
            self.state.configure(text=f"{self.engine}'s server isn't installed yet.")
            self.signs_in.configure(text="Install it, and its users and databases show up here.")
        else:
            text, ink = _STATE.get(state, (f"● {state or 'Unknown'}", None))
            self.state.configure(text=f"{text}   {service}", foreground=ink or self.state.cget("foreground"))
            self.signs_in.configure(text=f"Signs in {self.server.signs_in}.")
        running = state == "running"
        self.restart_button.label.configure(text="Restart" if running else "Start")
        self.restart_button.fit()
        self.restart_button.set_enabled(bool(service))
        self.restart_button.pack(side="right", padx=(px(8), 0)) if service else self.restart_button.pack_forget()
        self.load_button.set_enabled(running)
        self.load_button.pack(side="right", padx=(px(8), 0)) if service else self.load_button.pack_forget()
        self._show_listing()
        if service and not running:
            self.page.bar.say(f"{self.engine} isn't running: Start it, then Show users and databases.")
        elif service:
            self.page.bar.say(f"Show users and databases asks for {self.engine}'s own superuser password, once.")

    def _fill_picker(self):
        """More than one PostgreSQL installed: which one to manage."""
        if len(self.installs) < 2:
            self.picker.pack_forget()
            return
        menu = self.picker["menu"]
        menu.delete(0, "end")
        for install in self.installs:
            label = f"{install.name} (port {install.port})"
            menu.add_command(label=label, command=lambda i=install: self._on_pick(i))
        if isinstance(self.server, db.Postgres):
            self.picked.set(f"{self.server.install.name} (port {self.server.install.port})")
        self.picker.pack(side="right", padx=(px(8), 0))

    def _on_pick(self, install):
        self.server, self.listing = db.Postgres(install), None
        self.reload()

    def _restart(self):
        verb = self.restart_button.label.cget("text")
        if not confirm(self.page.winfo_toplevel(), f"{verb} {self.engine}?",
                       [f"{verb}-Service {self.service_name}", "",
                        "Anything connected to it (an app, a terminal) loses its connection for a moment.",
                        "Windows asks for permission, because a service belongs to the whole machine."], verb):
            return
        page = self.page
        page.set_busy(True)
        page.bar.pulse()
        page.bar.say(f"{verb}ing {self.service_name} · asks for permission")
        page.terminal.clear()

        def work():
            page.terminal.log(f"▶ {verb} {self.service_name}")
            page.terminal.log(f"$ {verb}-Service -Name '{self.service_name}'")
            _ok, text = db.restart(self.service_name, start_only=verb == "Start")
            if text:
                page.terminal.log(text)
            return self._read(), text

        page.run_async(work, self._on_restarted)

    def _on_restarted(self, result):
        read, text = result
        self.page.bar.done()
        self._on_read(read)
        if read[2][1] == "running":
            self.page.bar.say(f"Done: {self.service_name} is running.")
        else:
            self.page.bar.say(f"{self.service_name} isn't running: {tail(text, 1) or 'see the Terminal'}")

    # ---- the lists ----

    def _load(self):
        if self.server is not None and self.server.needs_password and not self._ask_password():
            return
        self._change("Reading users and databases", [], None)

    def _show_listing(self):
        for box in (self.users, self.databases):
            for child in box.winfo_children():
                child.destroy()
        loaded = self.listing is not None
        for button in (self.create_user_button, self.create_db_button):
            button.set_enabled(loaded)
        if not loaded:
            role(tk.Label(self.users, text="Show users and databases lists them here.", anchor="w",
                          justify="left", wraplength=px(300)), fg="dim").pack(fill="x")
            return
        system_users, system_dbs = db.SYSTEM_USERS[self.engine], db.SYSTEM_DATABASES[self.engine]
        for u in self.listing.users:
            detail = " · ".join(filter(None, [u.host and f"@{u.host}", u.note]))
            mine = u.name not in system_users
            self._row(self.users, u.name, detail, [
                *([("Check password", lambda u=u: self._check_password(u))]
                  if mine or u.name in ("root", "postgres") else []),  # the rest are locked: no sign-in
                *([("Change password", lambda u=u: self._change_password(u)),
                   ("Delete", lambda u=u: self._delete_user(u))] if mine else [])])
        for d in self.listing.databases:
            owner = (f"owner {d.owner}" if self.engine == db.POSTGRES else f"for {d.owner}") if d.owner else ""
            actions = [] if d.name in system_dbs else [("Delete", lambda d=d: self._delete_database(d))]
            self._row(self.databases, d.name, owner, actions)

    @staticmethod
    def _row(parent, name, detail, actions):
        row = tk.Frame(parent)
        row.pack(fill="x", pady=px(1))
        for text, callback in reversed(actions):  # packed from the right, so they read left to right
            Button(row, text, callback, "destructive" if text == "Delete" else "").pack(side="right", padx=(px(4), 0))
        tk.Label(row, text=name, font=FONTS["bold"], anchor="w").pack(side="left")
        if detail:
            role(tk.Label(row, text=f"  {detail}", anchor="w"), fg="dim").pack(side="left")

    def _user_names(self):
        return [u.name for u in self.listing.users]

    # ---- changes ----

    def _create_user(self):
        mysql = self.engine == db.MYSQL
        v = _form(self.page.winfo_toplevel(), f"Create a {self.engine} user", "Create user",
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
        v = _form(self.page.winfo_toplevel(), f"New password for {u.name}", "Change password",
                  [("password", "New password", "password"), ("again", "Again", "password")], _new_password)
        if not v:
            return
        pw = v["password"]
        sql = db.my_password(u.name, u.host, pw) if self.engine == db.MYSQL else db.pg_password(u.name, pw)
        self._change(f"Changing {u.name}'s password", sql, lambda l: l.user(u.name, u.host) is not None,
                     lambda: self.server.check_password(u.name, u.host, pw))

    def _check_password(self, u):
        v = _form(self.page.winfo_toplevel(), f"Check {u.name}'s password", "Check",
                  [("password", "Password", "password")], lambda v: "" if v["password"] else "Type the password.",
                  note="Signs in as them with it, then signs out. Nothing changes.")
        if not v:
            return
        self.page.set_busy(True)
        self.page.run_async(lambda: self.server.check_password(u.name, u.host, v["password"]),
                            lambda r: self._on_checked(u, r))

    def _on_checked(self, u, result):
        self.page.set_busy(False)
        works, why = result
        if works:
            self.page.bar.say(f"Right: {u.name} signs in with that password.")
        elif works is False:
            self.page.bar.say(f"Wrong: {u.name} doesn't sign in with that password.")
        else:
            self.page.bar.say(f"Couldn't check {u.name}'s password.")
            info(self.page.winfo_toplevel(), "Couldn't check it", tail(why, 4))

    def _delete_user(self, u):
        lines = ([f"DROP USER {u.name}@{u.host}", "", "Its databases stay; only the user and what it's allowed "
                  "to do go."] if self.engine == db.MYSQL else
                 [f"DROP ROLE {u.name}", "", "PostgreSQL refuses while it owns a database: delete those first."])
        if not confirm(self.page.winfo_toplevel(), f"Delete user {u.name}?", lines, "Delete"):
            return
        sql = db.my_drop_user(u.name, u.host) if self.engine == db.MYSQL else db.pg_drop_user(u.name)
        self._change(f"Deleting user {u.name}", sql, lambda l: l.user(u.name, u.host) is None)

    def _create_database(self):
        mysql = self.engine == db.MYSQL
        owners = [u.name for u in self.listing.users if not mysql or u.name not in db.SYSTEM_USERS[db.MYSQL]]
        owners = (["No one yet", *owners] if mysql else sorted(owners, key=lambda n: n != "postgres"))
        v = _form(self.page.winfo_toplevel(), f"Create a {self.engine} database", "Create database",
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
        if not confirm(self.page.winfo_toplevel(), f"Delete database {d.name}?",
                       [f"DROP DATABASE {d.name}", "", "Every table and row in it is deleted. This can't be undone."],
                       "Delete", critical_ack=f"I understand everything in {d.name} is deleted"):
            return
        sql = db.my_drop_database(d.name) if self.engine == db.MYSQL else db.pg_drop_database(d.name)
        self._change(f"Deleting database {d.name}", sql, lambda l: l.database(d.name) is None)

    def _change(self, heading, statements, took, sign_in=None):
        """The statements, then the listing whatever they did; whether it took
        is read from that listing (and, for a password, by signing in)."""
        page = self.page
        page.set_busy(True)
        page.bar.pulse()
        page.bar.say(heading)
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
        if not ok and self.server.wrong_password(err):
            if self._ask_password(again=True):
                self._change(heading, statements, took, sign_in)
            else:
                page.bar.say(f"{self.engine} needs its superuser password here; nothing was changed.")
            return
        if listing is not None:
            self.listing = listing
            self._show_listing()
        if not ok and any(s in err for s in _DISMISSED):
            page.bar.say("Cancelled: no permission was given, so nothing ran.")
        elif not done:
            first = next((line for line in err.splitlines() if "ERROR" in line), tail(err, 1))
            page.bar.say(f"{heading} didn't work: {db.shown(first) or 'see the Terminal'}")
            info(page.winfo_toplevel(), f"{heading} didn't work",
                 tail(db.shown(err), 4) or "It isn't in the list afterwards.")
        elif not statements:
            n, m = len(listing.users), len(listing.databases)
            page.bar.say(f"{n} user{'s' * (n != 1)}, {m} database{'s' * (m != 1)}.")
        elif signed_in is None or signed_in[0]:
            page.bar.say(f"Done: {heading.lower()}" + (", and it signs in with that password." if signed_in else "."))
        elif signed_in[0] is False:
            page.bar.say(f"{heading}: done, but signing in with that password fails.")
        else:
            page.bar.say(f"Done: {heading.lower()}. Couldn't test signing in: {tail(signed_in[1], 1)}")

    def _ask_password(self, again: bool = False) -> bool:
        """The server's own superuser password. Windows has no peer or socket
        authentication to stand in for it, so it's asked for once a visit."""
        who = "root" if self.engine == db.MYSQL else "postgres"
        v = _form(self.page.winfo_toplevel(), f"{self.engine}'s {who} password", "Sign in",
                  [("password", f"{who}'s password", "password")], lambda v: "" if v["password"] else "Type it.",
                  note=("That password wasn't right. " if again else "") +
                       f"{self.engine} on Windows has no password-free way in, so it needs the password set for "
                       f"{who} when it was installed. It's kept in memory until you leave these details, never "
                       "saved and never shown in the Terminal.")
        if not v:
            return False
        if self.engine == db.MYSQL:
            self.server.root_password = v["password"]
        else:
            self.server.superuser_password = v["password"]
        self.signs_in.configure(text=f"Signs in {self.server.signs_in}.")
        return True
