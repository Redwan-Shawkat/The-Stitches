"""MySQL's and PostgreSQL's users and databases, and their service: what their
App Manager details list and change, as on Linux. Every statement is built
here from a fixed template and names that passed `valid_name`; a password only
ever goes in quoted (PostgreSQL gets a SCRAM hash of it, as psql's \\password
sends) and travels in the client's environment, never on a command line, on
disk or into the Terminal (`shown` hides it). Each change is followed by the
listing whatever it did, and that listing is how the panel checks it took.
Pure helpers first, then the subprocess calls.

Windows signs in differently from Linux, and that's the whole platform leaf:
there is no peer authentication and no socket to trust, so both servers want
a password for their superuser and the panel asks for it once per visit.
See ai-knowledgebase.md ("Windows: Databases")."""

import base64
import hashlib
import hmac
import os
import re
import secrets
import shutil
import subprocess
import unicodedata
import winreg
from dataclasses import dataclass, field
from pathlib import Path

from .elevate import powershell

_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,31}\Z")  # 32: MySQL's limit for a user name
_HOST_RE = re.compile(r"[A-Za-z0-9.%_:-]{1,255}\Z")
_SECRET_RE = re.compile(r"(PASSWORD|IDENTIFIED BY) '(?:[^'\\]|\\.|'')*'")

MYSQL, POSTGRES = "MySQL", "PostgreSQL"
# Theirs, not anyone's app: no delete, and no password change.
SYSTEM_USERS = {MYSQL: {"root", "mysql.sys", "mysql.session", "mysql.infoschema"},
                POSTGRES: {"postgres"}}
SYSTEM_DATABASES = {MYSQL: {"mysql", "sys", "information_schema", "performance_schema"}, POSTGRES: {"postgres"}}


@dataclass
class User:
    name: str
    host: str = ""  # MySQL's: a user is a name at a host
    note: str = ""  # "superuser", "can't sign in"


@dataclass
class Database:
    name: str
    owner: str = ""  # PostgreSQL's owner; for MySQL, the users granted on it


@dataclass
class Listing:
    users: list[User] = field(default_factory=list)
    databases: list[Database] = field(default_factory=list)

    def user(self, name, host=""):
        return next((u for u in self.users if u.name == name and (not host or u.host == host)), None)

    def database(self, name):
        return next((d for d in self.databases if d.name == name), None)


@dataclass
class Install:
    """One PostgreSQL version installed: EDB's installer gives each its own
    service, port and folder. Linux's Cluster, named after what Windows has."""

    version: str
    port: str
    service: str
    folder: str = ""  # its base directory, where bin\\psql.exe lives

    @property
    def name(self) -> str:
        return f"PostgreSQL {self.version}"


def valid_name(name: str) -> str:
    """Why `name` can't be a user or database name, or "" when it can."""
    if not name:
        return "Type a name."
    if not _NAME_RE.match(name):
        return "Use letters, digits, _ and - only, start with a letter or _, at most 32."
    return ""


def valid_password(password: str, again: str) -> str:
    if not password:
        return "Type a password."
    if password != again:
        return "The two passwords aren't the same."
    if any(unicodedata.category(c) == "Cc" for c in password):
        return "A password can't have tabs, new lines or other control characters."
    return ""


def shown(sql: str) -> str:
    """`sql` as the Terminal shows it: every password hidden."""
    return _SECRET_RE.sub(r"\1 '••••••'", sql)


def parse_listing(text: str) -> Listing:
    """Rows of "u<TAB>name<TAB>host or note" and "d<TAB>name<TAB>owner", as
    the listing queries below print them."""
    listing = Listing()
    for line in text.splitlines():
        parts = (line.split("\t") + ["", ""])[:3]
        if parts[0] == "u":  # MySQL's third column is "@host", PostgreSQL's a note
            host, note = (parts[2][1:], "") if parts[2].startswith("@") else ("", parts[2])
            listing.users.append(User(parts[1], host, note))
        elif parts[0] == "d":
            listing.databases.append(Database(parts[1], parts[2]))
    return listing


def parse_service(text: str) -> str:
    """`Get-Service -Name x | Select Status`'s word, lowercased to read as
    Linux's ActiveState does: "running", "stopped", or "" when there's no
    such service."""
    word = text.strip().splitlines()[-1].strip().lower() if text.strip() else ""
    return word if word in ("running", "stopped", "paused", "startpending", "stoppending") else ""


# ---- PostgreSQL's statements ----

PG_LIST = ("SELECT 'u', rolname, CASE WHEN rolsuper THEN 'superuser' WHEN NOT rolcanlogin THEN 'can''t sign in' "
           "ELSE '' END FROM pg_roles WHERE rolname !~ '^pg_' "
           "UNION ALL SELECT 'd', datname, pg_get_userbyid(datdba) FROM pg_database WHERE NOT datistemplate "
           "ORDER BY 1, 2;")


def scram(password: str, salt: bytes | None = None, iterations: int = 4096) -> str:
    """The SCRAM-SHA-256 verifier PostgreSQL stores for `password`. Sent
    instead of the password, so not even a failed statement in the server's
    log has it. ponytail: NFKC stands in for SASLprep; a password with
    unusual Unicode spaces or controls could then not sign in (controls are
    refused by valid_password)."""
    salt = salt or secrets.token_bytes(16)
    salted = hashlib.pbkdf2_hmac("sha256", unicodedata.normalize("NFKC", password).encode(), salt, iterations)
    stored = hashlib.sha256(hmac.digest(salted, b"Client Key", "sha256")).digest()
    server = hmac.digest(salted, b"Server Key", "sha256")
    b64 = lambda b: base64.b64encode(b).decode()
    return f"SCRAM-SHA-256${iterations}:{b64(salt)}${b64(stored)}:{b64(server)}"


def _pg_id(name: str) -> str:
    """Quoted, so any name the server lists is one name (and "-" is fine)."""
    return '"' + name.replace('"', '""') + '"'


def pg_create_user(name: str, password: str, with_database: bool) -> list[str]:
    sql = [f"CREATE ROLE {_pg_id(name)} LOGIN PASSWORD '{scram(password)}';"]
    return sql + pg_create_database(name, name) if with_database else sql


def pg_password(name: str, password: str) -> list[str]:
    return [f"ALTER ROLE {_pg_id(name)} PASSWORD '{scram(password)}';"]


def pg_drop_user(name: str) -> list[str]:
    return [f"DROP ROLE {_pg_id(name)};"]


def pg_create_database(name: str, owner: str) -> list[str]:
    return [f"CREATE DATABASE {_pg_id(name)}" + (f" OWNER {_pg_id(owner)}" if owner else "") + ";"]


def pg_drop_database(name: str) -> list[str]:
    return [f"DROP DATABASE {_pg_id(name)};"]


# ---- MySQL's statements ----

# Backslash escapes mean the same in every session, whatever the server's sql_mode.
MY_SESSION = "SET SESSION sql_mode = REPLACE(@@sql_mode, 'NO_BACKSLASH_ESCAPES', '');"
MY_LIST = ("SELECT 'u', user, CONCAT('@', host) FROM mysql.user "
           "UNION ALL SELECT 'd', s.schema_name, IFNULL(GROUP_CONCAT(DISTINCT d.user ORDER BY d.user), '') "
           "FROM information_schema.schemata s LEFT JOIN mysql.db d "
           # a grant's database name has _ and % escaped (they're wildcards there)
           "ON REPLACE(REPLACE(d.db, CONCAT(CHAR(92), '_'), '_'), CONCAT(CHAR(92), '%'), '%') COLLATE utf8mb3_bin "
           "= s.schema_name COLLATE utf8mb3_bin GROUP BY s.schema_name "
           "ORDER BY 1, 2;")


def _my_str(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _my_id(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def _my_account(name: str, host: str) -> str:
    if not _HOST_RE.match(host):
        raise ValueError(f"not a host: {host!r}")
    return f"{_my_str(name)}@{_my_str(host)}"


def my_create_user(name: str, password: str, with_database: bool, host: str = "localhost") -> list[str]:
    sql = [f"CREATE USER {_my_account(name, host)} IDENTIFIED BY {_my_str(password)};"]
    return sql + my_create_database(name, name, host) if with_database else sql


def my_password(name: str, host: str, password: str) -> list[str]:
    return [f"ALTER USER {_my_account(name, host)} IDENTIFIED BY {_my_str(password)};"]


def my_drop_user(name: str, host: str) -> list[str]:
    return [f"DROP USER {_my_account(name, host)};"]


def my_create_database(name: str, owner: str, host: str = "localhost") -> list[str]:
    sql = [f"CREATE DATABASE {_my_id(name)};"]
    pattern = _my_id(name.replace("\\", "\\\\").replace("_", "\\_").replace("%", "\\%"))  # just this one
    return sql + [f"GRANT ALL PRIVILEGES ON {pattern}.* TO {_my_account(owner, host)};"] if owner else sql


def my_drop_database(name: str) -> list[str]:
    return [f"DROP DATABASE {_my_id(name)};"]


def my_error(text: str) -> str:
    """"ERROR 1045 (28000): Access denied…" -> "1045"."""
    m = re.search(r"ERROR (\d+)", text)
    return m.group(1) if m else ""


def find_client(name: str, folders=()) -> str:
    """A client on PATH, or in one of `folders`' bin. MySQL's and
    PostgreSQL's Windows installers don't always put theirs on PATH."""
    found = shutil.which(name)
    if found:
        return found
    for folder in folders:
        exe = Path(folder, "bin", f"{name}.exe")
        if exe.is_file():
            return str(exe)
    return ""


# ---- IO below ----


def _client(argv, sql="", env=None) -> tuple[bool, str, str]:
    """(succeeded, stdout, stderr) of a database client reading `sql` on
    stdin. A password reaches it through `env` only: not on the command line,
    where any other process could read it, and not through an option file,
    which would put it on the disk."""
    if not argv or not argv[0]:
        return False, "", "That client isn't installed, or isn't on PATH."
    try:
        p = subprocess.run(argv, input=sql, capture_output=True, text=True, errors="replace",
                           env=dict(os.environ, **(env or {})), timeout=120, check=False,
                           creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, "", str(exc)
    return p.returncode == 0, p.stdout, p.stderr.strip()


def service_state(*names) -> tuple[str, str]:
    """(the first of `names` that exists, its state). As on Linux, where it's
    the first loaded systemd unit of several possible ones."""
    for name in names:
        _code, out = powershell(f"(Get-Service -Name '{name}' -ErrorAction SilentlyContinue).Status")
        state = parse_service(out)
        if state:
            return name, state
    return "", ""


def restart(service: str, start_only: bool = False) -> tuple[bool, str]:
    """Start or restart a Windows service: that needs admin, so it goes
    through the same UAC prompt as every other elevated action."""
    verb = "Start-Service" if start_only else "Restart-Service"
    code, out = powershell(f"{verb} -Name '{service}' -ErrorAction Stop", elevated=True)
    return code == 0, out.strip()


class Postgres:
    """Over TCP as the postgres superuser, with its password: Windows has no
    peer authentication, so unlike Linux there is no password-free way in.
    `superuser_password` is asked for once and kept for this visit only."""

    engine = POSTGRES

    def __init__(self, install: Install, psql=(), host="localhost", user="postgres"):
        self.install, self.host, self.user = install, host, user
        self.psql = list(psql) or [find_client("psql", [install.folder])]
        self.superuser_password = None

    @property
    def signs_in(self):
        return (f"as {self.user} over {self.host}:{self.install.port}, with the password you typed "
                "(kept until you leave these details)")

    @property
    def needs_password(self) -> bool:
        return self.superuser_password is None

    def service(self) -> tuple[str, str]:
        return service_state(self.install.service)

    def _flags(self) -> list[str]:
        return ["-X", "-q", "-A", "-t", "-F", "\t", "-v", "ON_ERROR_STOP=1", "-w",
                "-h", self.host, "-p", self.install.port, "-U", self.user, "-d", "postgres"]

    def run(self, statements=()) -> tuple[bool, Listing | None, str]:
        """(the statements all ran, the listing after them, what went wrong).

        The listing runs whatever the statements did, so a half-done change
        still shows what's there now and "did it work" is read from the
        listing, never from an exit code. Linux puts both in one `sh -c` to
        spend one pkexec prompt; here the password is already in hand, so two
        plain calls do the same job without a shell."""
        env = {"PGPASSWORD": self.superuser_password or "", "PGCONNECT_TIMEOUT": "5"}
        ok, err = True, ""
        if statements:
            ok, _out, err = _client([*self.psql, *self._flags()], "\n".join(statements) + "\n", env)
        listed, out, list_err = _client([*self.psql, *self._flags(), "-c", PG_LIST], env=env)
        # With nothing to run, whether the listing came back is the answer:
        # saying "it worked" while the server refused the sign-in would lie.
        return (ok if statements else listed), parse_listing(out) if out.strip() else None, err or list_err

    def wrong_password(self, err: str) -> bool:
        return "password authentication failed" in err or "no password supplied" in err

    def check_password(self, user: str, _host: str, password: str) -> tuple[bool | None, str]:
        """True: it signs in; False: wrong password; None: can't tell (why)."""
        ok, _out, err = _client([*self.psql, "-X", "-w", "-h", self.host, "-p", self.install.port, "-U", user,
                                 "-d", "postgres", "-c", "SELECT 1"],
                                env={"PGPASSWORD": password, "PGCONNECT_TIMEOUT": "5"})
        if ok:
            return True, ""
        if "password authentication failed" in err:
            return False, ""
        return None, err


class MySQL:
    """As MySQL's root over TCP, with root's password: Windows has no
    auth_socket, so unlike Linux root always has one. It's asked for once and
    kept for this visit only."""

    engine = MYSQL

    def __init__(self, client=(), host="localhost", port="3306", user="root"):
        self.host, self.port, self.user = host, port, user
        self.client = list(client) or [find_client("mysql", _mysql_folders())]
        self.root_password = None

    @property
    def signs_in(self):
        return (f"as {self.user} over {self.host}:{self.port}, with the password you typed "
                "(kept until you leave these details)")

    @property
    def needs_password(self) -> bool:
        return self.root_password is None

    def service(self) -> tuple[str, str]:
        return service_state("MySQL80", "MySQL84", "MySQL", "MariaDB")

    def _flags(self) -> list[str]:
        return ["-N", "-B", "-h", self.host, "-P", self.port, "-u", self.user, "--connect-timeout=5"]

    def run(self, statements=()) -> tuple[bool, Listing | None, str]:
        env = {"MYSQL_PWD": self.root_password or ""}
        ok, err = True, ""
        if statements:
            sql = "\n".join([MY_SESSION, *statements]) + "\n"
            ok, _out, err = _client([*self.client, *self._flags()], sql, env)
        listed, out, list_err = _client([*self.client, *self._flags(), "-e", MY_LIST], env=env)
        return (ok if statements else listed), parse_listing(out) if out.strip() else None, err or list_err

    def wrong_password(self, err: str) -> bool:
        return my_error(err) in ("1045", "1698")

    def check_password(self, user: str, host: str, password: str) -> tuple[bool | None, str]:
        if host not in ("localhost", "%", self.host):
            return None, f"{user}@{host} can only sign in from {host}"
        ok, _out, err = _client([*self.client, "-N", "-B", "-h", self.host, "-P", self.port, "-u", user,
                                 "--connect-timeout=5", "-e", "SELECT 1"], env={"MYSQL_PWD": password})
        if ok:
            return True, ""
        if my_error(err) == "1045":
            return False, ""
        if my_error(err) == "1698":
            return None, f"{user} signs in through its system account, not a password"
        return None, err


def _registry_values(root: int, path: str) -> list[dict[str, str]]:
    """Every subkey of `path` as its values, or [] when there's no such key."""
    found = []
    try:
        with winreg.OpenKey(root, path) as key:
            for i in range(winreg.QueryInfoKey(key)[0]):
                with winreg.OpenKey(key, winreg.EnumKey(key, i)) as sub:
                    values = {}
                    for v in range(winreg.QueryInfoKey(sub)[1]):
                        name, value, _kind = winreg.EnumValue(sub, v)
                        values[name] = str(value)
                    found.append(values)
    except OSError:
        return []
    return found


def _mysql_folders() -> list[str]:
    """Where MySQL's own installer records its server, for mysql.exe."""
    return [v["Location"] for v in _registry_values(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\MySQL AB")
            if v.get("Location")]


def pg_installs() -> list[Install]:
    """Each PostgreSQL version installed, with its port and service. EDB's
    installer records them here; the service it registers is named after the
    major version. Linux reads `pg_lsclusters` for the same thing."""
    installs = []
    for values in _registry_values(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\PostgreSQL\Installations"):
        version = values.get("Version", "")
        if not version:
            continue
        major = version.split(".")[0]
        installs.append(Install(version, values.get("Port", "5432"), f"postgresql-x64-{major}",
                                values.get("Base Directory", "")))
    return sorted(installs, key=lambda i: i.version)
