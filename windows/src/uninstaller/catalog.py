"""The App Manager's catalog, as on Linux: every app Stitches can install, and
its winget id. Static on purpose: adding an app means adding a line here and
releasing, never a download or a text box, so only these ids are ever passed
to winget. `about`, `site` and `setup` are what the app's details show.
See ai-knowledgebase.md ("Windows: App Manager")."""

import re
from dataclasses import dataclass
from pathlib import Path

CATEGORIES = ("Development", "Developer Tools", "Databases", "Browsers", "Office", "Media", "Games",
              "Networking", "Utilities")

ICONS = Path(__file__).parent / "appicons"  # one 64px PNG per app, named after it


@dataclass(frozen=True)
class App:
    name: str
    description: str
    category: str
    package: str  # the winget id, from the winget source
    command: str = ""  # on PATH when installed some other way (a zip, Scoop, an old installer)
    version: tuple = ()  # what prints that command's version; (command, "--version") when empty
    about: str = ""  # a few lines for its details view: what it is and what it's for
    site: str = ""  # its own download page, for installing it some other way
    setup: tuple = ()  # steps after installing, before it's usable; shown in its details

    @property
    def icon(self) -> Path:
        return ICONS / f"{re.sub(r'[^a-z0-9]+', '-', self.name.lower()).strip('-')}.png"


CATALOG = (
    App("Visual Studio Code", "Code editor", "Development", "Microsoft.VisualStudioCode", command="code",
        about=("Microsoft's free code editor: an editor, a terminal, Git and debugging in one window, with "
               "extensions for almost every language."),
        site="https://code.visualstudio.com/docs/setup/windows"),
    App("Android Studio", "Android app development", "Development", "Google.AndroidStudio",
        about="Google's IDE for Android apps, with the Android SDK, an emulator and a layout editor.",
        site="https://developer.android.com/studio/install"),
    App("Postman", "API testing", "Development", "Postman.Postman",
        about=("Sends requests to web APIs and shows the answers, so you can build and test an API without "
               "writing a client."),
        site="https://www.postman.com/downloads/"),
    App("Git", "Version control", "Development", "Git.Git", command="git",
        about=("Keeps the history of a project's files, so you can go back, branch, merge, and share the work "
               "through GitHub or GitLab. Brings Git Bash with it."),
        site="https://git-scm.com/download/win"),
    App("GitHub CLI", "GitHub from the terminal", "Development", "GitHub.cli", command="gh",
        about="The gh command: pull requests, issues, releases and Actions from the terminal.",
        site="https://github.com/cli/cli#windows"),
    App("Docker Desktop", "Containers, with Compose", "Development", "Docker.DockerDesktop", command="docker",
        about=("Runs apps in containers: each with its own files and libraries, the same on every machine. "
               "Compose starts several together from one compose.yaml."),
        site="https://docs.docker.com/desktop/install/windows-install/",
        setup=("Windows needs WSL 2 for Docker's Linux containers. Docker Desktop installs it, but asks for a "
               "restart the first time.",
               "Open Docker Desktop once and accept its terms; the docker command only works while it runs.")),

    App("Node.js", "JavaScript runtime, with npm", "Developer Tools", "OpenJS.NodeJS.LTS", command="node",
        about=("Runs JavaScript outside the browser: web servers, build tools and command-line programs. npm, "
               "its package manager, comes with it."),
        site="https://nodejs.org/en/download"),
    App("Yarn", "Node.js packages, faster", "Developer Tools", "Yarn.Yarn", command="yarn",
        about="Another package manager for Node.js projects, faster than npm on big projects.",
        site="https://yarnpkg.com/getting-started/install"),
    App("pnpm", "Node.js packages, sharing one store", "Developer Tools", "pnpm.pnpm", command="pnpm",
        about=("A package manager for Node.js projects that keeps one copy of every package on the disk and "
               "links it into each project, so installs are fast and small."),
        site="https://pnpm.io/installation"),
    App("Go", "The Go language", "Developer Tools", "GoLang.Go", command="go", version=("go", "version"),
        about="Google's language for servers and command-line tools; builds one fast binary with no dependencies.",
        site="https://go.dev/doc/install"),
    App("Rust", "rustup, the Rust compiler and Cargo", "Developer Tools", "Rustlang.Rustup", command="rustc",
        about=("A fast language that catches memory bugs when it compiles. rustup installs the compiler (rustc) "
               "and its build tool and package manager (Cargo)."),
        site="https://www.rust-lang.org/tools/install",
        setup=("Rust needs a C linker. Install the Visual Studio Build Tools with the \"Desktop development with "
               "C++\" workload if rustc says link.exe is missing.",)),
    App("PHP", "PHP from the command line", "Developer Tools", "PHP.PHP.8.3", command="php",
        about=("The language behind WordPress and Laravel. Here it's the php command, for running scripts and "
               "PHP's own built-in web server."),
        site="https://windows.php.net/download/"),
    App("Python", "Python 3, with pip", "Developer Tools", "Python.Python.3.13", command="python",
        about=("A general-purpose language for scripts, web apps, data and AI. pip, its package installer, comes "
               "with it; use it inside a virtual environment (python -m venv)."),
        site="https://www.python.org/downloads/windows/"),
    App("Java", "The Java development kit (Temurin)", "Developer Tools", "EclipseAdoptium.Temurin.21.JDK",
        command="java", version=("java", "-version"),
        about=("Eclipse Temurin, a build of OpenJDK: the compiler and runtime for Java programs, and what Maven, "
               "Gradle and Android builds need."),
        site="https://adoptium.net/temurin/releases/"),

    App("MySQL", "Database server", "Databases", "Oracle.MySQL", command="mysqld",
        about=("A database server: tables queried with SQL. Most PHP and Laravel apps use it. Its users and "
               "databases are managed below."),
        site="https://dev.mysql.com/downloads/installer/",
        setup=("MySQL's installer asks for a root password and whether to run as a Windows service. Keep the "
               "service on, or nothing can connect.",)),
    App("PostgreSQL", "Database server", "Databases", "PostgreSQL.PostgreSQL.17", command="psql",
        about=("A database server with strict SQL, JSON columns and many extensions. Its users (roles) and "
               "databases are managed below."),
        site="https://www.postgresql.org/download/windows/",
        setup=("PostgreSQL's installer asks for the postgres superuser's password. Stitches needs it to list and "
               "change users and databases.",)),

    App("Brave", "Web browser that blocks ads", "Browsers", "Brave.Brave",
        about="A Chromium-based browser that blocks ads and trackers by itself. Web Apps can run on it.",
        site="https://brave.com/download/"),
    App("Google Chrome", "Web browser", "Browsers", "Google.Chrome",
        about="Google's browser, the one most sites are tested against. Web Apps can run on it.",
        site="https://www.google.com/chrome/"),

    App("LibreOffice", "Documents, spreadsheets, slides", "Office", "TheDocumentFoundation.LibreOffice",
        about=("A free office suite: Writer for documents, Calc for spreadsheets, Impress for slides. Opens "
               "Microsoft Office files."),
        site="https://www.libreoffice.org/download/download-libreoffice/"),
    App("ONLYOFFICE", "Office suite that reads Microsoft formats", "Office", "ONLYOFFICE.DesktopEditors",
        about=("An office suite that looks like Microsoft Office and keeps .docx, .xlsx and .pptx files closest "
               "to how Office shows them."),
        site="https://www.onlyoffice.com/download-desktop.aspx"),

    App("VLC", "Plays any video or audio", "Media", "VideoLAN.VLC",
        about="Plays almost any video or audio file, disc or stream, with no extra codecs to install.",
        site="https://www.videolan.org/vlc/download-windows.html"),
    App("Spotify", "Music streaming", "Media", "Spotify.Spotify",
        about="Spotify's own app for music and podcasts.",
        site="https://www.spotify.com/download/windows/"),
    App("Kdenlive", "Video editor", "Media", "KDE.Kdenlive",
        about="A video editor with a timeline, effects and transitions, from KDE.",
        site="https://kdenlive.org/en/download/"),
    App("Pinta", "Paint program", "Media", "Pinta.Pinta",
        about=("A simple paint program, like Paint but with layers and effects: draw, crop, resize and add text, "
               "and undo as far back as you like."),
        site="https://www.pinta-project.com/releases/"),

    App("Epic Games Launcher", "Epic Games Store, and its free games", "Games", "EpicGames.EpicGamesLauncher",
        about="Epic's store and launcher, with a game given away free every week.",
        site="https://store.epicgames.com/en-US/download"),

    App("qBittorrent", "Torrent downloads", "Networking", "qBittorrent.qBittorrent",
        about="Downloads torrents, with no ads, and a search across torrent sites.",
        site="https://www.qbittorrent.org/download"),
    App("LocalSend", "Send files to nearby devices", "Networking", "LocalSend.LocalSend",
        about="Sends files and text to phones and computers on the same Wi-Fi, with no account and no cable.",
        site="https://localsend.org/download"),
    App("AnyDesk", "Remote desktop", "Networking", "AnyDesk.AnyDesk",
        about="Remote desktop: control another computer, or let someone help on yours.",
        site="https://anydesk.com/en/downloads/windows"),
    App("Cloudflare WARP", "The free 1.1.1.1 VPN", "Networking", "Cloudflare.Warp", command="warp-cli",
        about=("Cloudflare's 1.1.1.1 app: encrypts your traffic and sends it through Cloudflare, free and with "
               "no account. winget calls it the Cloudflare One Client."),
        site="https://developers.cloudflare.com/warp-client/get-started/windows/",
        setup=("Open 1.1.1.1 from the Start menu and accept the terms, once.",
               "Turn it on with the switch in the app, or from its icon near the clock.",
               "From a terminal instead: warp-cli connect, warp-cli status, warp-cli disconnect.")),

    App("rclone", "Sync with cloud storage", "Utilities", "Rclone.Rclone", command="rclone",
        version=("rclone", "version"),
        about=("Copies and syncs files with Google Drive, OneDrive, Dropbox, S3 and dozens more, from the "
               "terminal."),
        site="https://rclone.org/install/"),
    App("7-Zip", "Opens and makes zip, 7z and rar files", "Utilities", "7zip.7zip",
        about="Opens and makes zip, 7z, rar, tar and iso files, and adds itself to Explorer's right-click menu.",
        site="https://www.7-zip.org/download.html"),
    App("Notepad++", "Text and code editor", "Utilities", "Notepad++.Notepad++",
        about="A fast text editor with tabs, syntax colouring and search across files.",
        site="https://notepad-plus-plus.org/downloads/"),
    App("Avro Keyboard", "Bangla typing", "Utilities", "OmicronLab.Avro",
        about=('Type Bangla by spelling it in English letters: "ami" becomes আমি. Avro Phonetic is its default '
               "layout; fixed layouts (Bijoy, National) are in there too."),
        site="https://www.omicronlab.com/avro-keyboard.html",
        setup=("Open Avro Keyboard from the Start menu. It sits near the clock and starts with Windows.",
               "Switch between Bangla and English with F12 (or Ctrl+Alt+B, if F12 is taken).",
               "Pick the layout from its bar: Avro Phonetic types Bangla from English spelling.",
               "Install Bangla fonts from its Tools menu if Bangla text shows as boxes.")),
)
