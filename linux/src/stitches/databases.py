"""MySQL's and PostgreSQL's users and databases, and their service: what their
App Manager details list and change. Every statement is built here from a
fixed template and names that passed `valid_name`; a password only ever goes
in quoted (PostgreSQL gets a SCRAM hash of it, as psql's \\password sends) and
travels on stdin or through a pipe, never on a command line, on disk or into
the Terminal (`shown` hides it). Each change runs with the listing after it,
in one call and so one password prompt, and that listing is how the panel
checks it took. Pure helpers first, then the subprocess calls.
See ai-knowledgebase.md ("Databases")."""

import base64
import hashlib
import hmac
import os
import re
import secrets
import shlex
import subprocess
import unicodedata
from dataclasses import dataclass, field

_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,31}\Z")  # 32: MySQL's limit for a user name
_HOST_RE = re.compile(r"[A-Za-z0-9.%_:-]{1,255}\Z")
_SECRET_RE = re.compile(r"(PASSWORD|IDENTIFIED BY) '(?:[^'\\]|\\.|'')*'")

MYSQL, POSTGRES = "MySQL", "PostgreSQL"
# Theirs, not anyone's app: no delete, and no password change (root signs in
# through its socket on Ubuntu, and a password would switch that off).
SYSTEM_USERS = {MYSQL: {"root", "mysql.sys", "mysql.session", "mysql.infoschema", "debian-sys-maint"},
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
class Cluster:
    version: str
    name: str
    port: str
    online: bool

    @property
    def unit(self):
        return f"postgresql@{self.version}-{self.name}.service"


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


def parse_clusters(text: str) -> list[Cluster]:
    """`pg_lsclusters -h`: "18 main 5432 online postgres /var/lib/... /var/log/..."."""
    rows = [line.split() for line in text.splitlines()]
    return [Cluster(r[0], r[1], r[2], r[3].startswith("online")) for r in rows if len(r) >= 4]


def parse_unit(text: str) -> tuple[str, str]:
    """`systemctl show -p Id,LoadState,ActiveState a.service b.service`: the
    first unit that exists, and its state ("" when neither does)."""
    for block in text.strip().split("\n\n"):
        props = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
        if props.get("LoadState") == "loaded":
            return props.get("Id", ""), props.get("ActiveState", "")
    return "", ""


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


def my_option_file(user: str, password: str) -> str:
    """For --defaults-extra-file, handed over through a pipe."""
    quoted = password.replace("\\", "\\\\").replace('"', '\\"')
    return f'[client]\nuser={user}\npassword="{quoted}"\n'


def my_error(text: str) -> str:
    """"ERROR 1045 (28000): Access denied…" -> "1045"."""
    m = re.search(r"ERROR (\d+)", text)
    return m.group(1) if m else ""


# ---- IO below ----


def _client(argv, sql="", option_file=None, env=None) -> tuple[bool, str, str]:
    """(succeeded, stdout, stderr) of a database client reading `sql` on stdin.
    An option file goes through a pipe as /dev/fd/N, never onto disk."""
    fds = ()
    if option_file is not None:
        read, write = os.pipe()
        os.write(write, option_file.encode())
        os.close(write)
        fds = (read,)
        argv = [argv[0], f"--defaults-extra-file=/dev/fd/{read}", *argv[1:]]  # it has to come first
    try:
        p = subprocess.run(argv, input=sql, capture_output=True, text=True, errors="replace", pass_fds=fds, cwd="/",
                           env=dict(os.environ, LC_ALL="C", **(env or {})), timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, "", str(exc)
    finally:
        for fd in fds:
            os.close(fd)
    return p.returncode == 0, p.stdout, p.stderr.strip()


def _unit_state(*units) -> tuple[str, str]:
    _ok, out, _err = _client(["systemctl", "show", "-p", "Id,LoadState,ActiveState", *units])
    return parse_unit(out)


def restart(unit: str) -> tuple[bool, str]:
    ok, out, err = _client(["pkexec", "systemctl", "restart", unit])
    return ok, (out + err).strip()


def _then_list(client, listing: str, flag: str) -> str:
    """A script that runs the statements on stdin, then the listing even when
    one failed (so the lists show what did change), exiting as the first did."""
    c = shlex.join(client)
    return f'{c} "$@"; rc=$?; {c} "$@" {flag} {shlex.quote(listing)}; exit $rc'


class Postgres:
    """As the postgres system user through pkexec: Ubuntu's PostgreSQL trusts
    it by peer authentication, so no database password is needed."""

    engine = POSTGRES

    def __init__(self, cluster: Cluster, sudo=("pkexec", "runuser", "-u", "postgres", "--"), psql=("psql",),
                 host="localhost"):
        self.cluster, self.sudo, self.psql, self.host = cluster, sudo, psql, host

    @property
    def signs_in(self):
        return "as the postgres system user (peer), through pkexec"

    def service(self) -> tuple[str, str]:
        return _unit_state(self.cluster.unit)

    def run(self, statements=()) -> tuple[bool, Listing | None, str]:
        """(the statements all ran, the listing after them, what went wrong)."""
        flags = ["-X", "-q", "-A", "-t", "-F", "\t", "-v", "ON_ERROR_STOP=1", "-p", self.cluster.port, "-d", "postgres"]
        ok, out, err = _client([*self.sudo, "sh", "-c", _then_list(self.psql, PG_LIST, "-c"), "sh", *flags],
                               "\n".join(statements) + "\n")
        return ok, parse_listing(out) if out.strip() else None, err

    def check_password(self, user: str, _host: str, password: str) -> tuple[bool | None, str]:
        """True: it signs in; False: wrong password; None: can't tell (why)."""
        ok, _out, err = _client(["psql", "-X", "-w", "-h", self.host, "-p", self.cluster.port, "-U", user,
                                 "-d", "postgres", "-c", "SELECT 1"], env={"PGPASSWORD": password,
                                                                          "PGCONNECT_TIMEOUT": "5"})
        if ok:
            return True, ""
        if "password authentication failed" in err:
            return False, ""
        return None, err


class MySQL:
    """As MySQL's root: through its socket as the root system user (Ubuntu's
    auth_socket) by default, or with root's password when that's how this
    server is set up (then `root_password` is set, for this visit only)."""

    engine = MYSQL

    def __init__(self, sudo=("pkexec",), client=("mysql",)):
        self.sudo, self.client = sudo, client  # client gets --socket= in the tests
        self.root_password = None

    @property
    def signs_in(self):
        return ("as root, with the password you typed (kept until you leave these details)" if self.root_password
                else "as root, through MySQL's socket and pkexec")

    def service(self) -> tuple[str, str]:
        return _unit_state("mysql.service", "mariadb.service")

    def run(self, statements=()) -> tuple[bool, Listing | None, str]:
        sql = "\n".join([MY_SESSION, *statements]) + "\n"
        if self.root_password is None:
            ok, out, err = _client([*self.sudo, "sh", "-c", _then_list(self.client, MY_LIST, "-e"), "sh",
                                    "-u", "root", "-N", "-B"], sql)
        else:  # a pipe is read once: one each
            option_file = my_option_file("root", self.root_password)
            ok, _out, err = _client([*self.client, "-N", "-B"], sql, option_file)
            _listed, out, list_err = _client([*self.client, "-N", "-B", "-e", MY_LIST], option_file=option_file)
            err = err or list_err
        return ok, parse_listing(out) if out.strip() else None, err

    def needs_root_password(self, err: str) -> bool:
        """Root's socket sign-in refused: this server wants root's password."""
        return self.root_password is None and my_error(err) in ("1045", "1698")

    def check_password(self, user: str, host: str, password: str) -> tuple[bool | None, str]:
        if host not in ("localhost", "%"):
            return None, f"{user}@{host} can only sign in from {host}"
        ok, _out, err = _client([*self.client, "-N", "-B", "-e", "SELECT 1"], option_file=my_option_file(user, password))
        if ok:
            return True, ""
        if my_error(err) == "1045":
            return False, ""
        if my_error(err) == "1698":
            return None, f"{user} signs in through its system account (auth_socket), not a password"
        return None, err


def pg_clusters() -> list[Cluster]:
    """Each PostgreSQL version installed has its own cluster, server and port."""
    return parse_clusters(_client(["pg_lsclusters", "-h"])[1])
