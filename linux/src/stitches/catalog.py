"""The App Manager's catalog: every app Stitches can install, and how. It is
static on purpose: adding an app means adding a line here and releasing, never
a download or a text box, so only these commands can ever run.
See ai-knowledgebase.md ("App Manager")."""

import re
from dataclasses import dataclass
from pathlib import Path

APT, SNAP, FLATPAK = "APT", "Snap", "Flatpak"
SOURCES = (APT, SNAP, FLATPAK)
CATEGORIES = ("Development", "Developer Tools", "Databases", "Browsers", "Office", "Media", "Networking",
              "Utilities")

ICONS = Path(__file__).parent / "appicons"  # one 64px PNG per app, named after it


@dataclass(frozen=True)
class App:
    name: str
    description: str
    category: str
    source: str  # how Stitches installs it
    package: str  # the apt package, snap name or Flatpak app id
    classic: bool = False  # a snap that needs --classic
    also: tuple = ()  # (source, id) pairs it may already be installed through instead
    command: str = ""  # on PATH when installed some other way (nvm, rustup, a tarball)
    version: tuple = ()  # what prints that command's version; (command, "--version") when empty
    about: str = ""  # a few lines for its details view: what it is and what it's for
    site: str = ""  # its own install page, for installing it some other way
    repo: tuple = ()  # (name, key URL, repo URL): a vendor's APT repository, added before it installs
    setup: tuple = ()  # steps after installing, before it's usable; shown in its details

    @property
    def icon(self) -> Path:
        return ICONS / f"{re.sub(r'[^a-z0-9]+', '-', self.name.lower()).strip('-')}.png"


CATALOG = (
    App("Visual Studio Code", "Code editor", "Development", SNAP, "code", classic=True,
        also=((FLATPAK, "com.visualstudio.code"), (APT, "code")), command="code",
        about=("Microsoft's free code editor: an editor, a terminal, Git and debugging in one window, with "
               "extensions for almost every language."),
        site="https://code.visualstudio.com/docs/setup/linux"),
    App("Android Studio", "Android app development", "Development", SNAP, "android-studio", classic=True,
        also=((FLATPAK, "com.google.AndroidStudio"),),
        about="Google's IDE for Android apps, with the Android SDK, an emulator and a layout editor.",
        site="https://developer.android.com/studio/install"),
    App("Postman", "API testing", "Development", SNAP, "postman", also=((FLATPAK, "com.getpostman.Postman"),),
        about=("Sends requests to web APIs and shows the answers, so you can build and test an API without writing"
               " a client."),
        site="https://www.postman.com/downloads/"),
    App("Git", "Version control", "Development", APT, "git", command="git",
        about=("Keeps the history of a project's files, so you can go back, branch, merge, and share the work "
               "through GitHub or GitLab."),
        site="https://git-scm.com/download/linux"),
    App("GitHub CLI", "GitHub from the terminal", "Development", APT, "gh", command="gh",
        about='The gh command: pull requests, issues, releases and Actions from the terminal.',
        site="https://github.com/cli/cli/blob/trunk/docs/install_linux.md"),
    App("Docker", "Containers", "Development", APT, "docker.io",
        also=((APT, "docker-ce"), (SNAP, "docker")), command="docker",
        about='Runs apps in containers: each with its own files and libraries, the same on every machine.',
        site="https://docs.docker.com/engine/install/ubuntu/"),
    App("Docker Compose", "Multi-container apps", "Development", APT, "docker-compose-v2",
        also=((APT, "docker-compose-plugin"), (APT, "docker-compose")),
        about='Starts several containers together (an app, its database, a cache) from one compose.yaml.',
        site="https://docs.docker.com/compose/install/linux/"),

    App("Node.js", "JavaScript runtime", "Developer Tools", APT, "nodejs", also=((SNAP, "node"),), command="node",
        about='Runs JavaScript outside the browser: web servers, build tools and command-line programs.',
        site="https://nodejs.org/en/download"),
    App("npm", "Node.js packages", "Developer Tools", APT, "npm", command="npm",
        about="Node.js's package manager: installs the libraries a JavaScript project lists in package.json.",
        site="https://docs.npmjs.com/downloading-and-installing-node-js-and-npm"),
    App("Yarn", "Node.js packages, faster", "Developer Tools", APT, "yarnpkg", command="yarn",
        about='Another package manager for Node.js projects, faster than npm on big projects.',
        site="https://yarnpkg.com/getting-started/install"),
    App("Go", "The Go language", "Developer Tools", SNAP, "go", classic=True, also=((APT, "golang-go"),),
        command="go", version=("go", "version"),
        about="Google's language for servers and command-line tools; builds one fast binary with no dependencies.",
        site="https://go.dev/doc/install"),
    App("Rust", "The Rust compiler", "Developer Tools", APT, "rustc", also=((SNAP, "rustup"),), command="rustc",
        about='A fast language that catches memory bugs when it compiles. rustc is its compiler.',
        site="https://www.rust-lang.org/tools/install"),
    App("Cargo", "Rust packages and builds", "Developer Tools", APT, "cargo", command="cargo",
        about="Rust's build tool and package manager: builds the project and fetches its crates.",
        site="https://doc.rust-lang.org/cargo/getting-started/installation.html"),
    App("PHP", "PHP from the command line", "Developer Tools", APT, "php-cli", also=((APT, "php"),),
        command="php",
        about=("The language behind WordPress and Laravel. Here it's the php command; its extensions are switched "
               "on and off below."),
        site="https://www.php.net/manual/en/install.unix.debian.php"),
    App("Composer", "PHP packages", "Developer Tools", APT, "composer", command="composer",
        about=("PHP's package manager: installs the libraries a PHP project lists in composer.json, and creates "
               "Laravel projects."),
        site="https://getcomposer.org/download/"),
    App("Python", "Python 3", "Developer Tools", APT, "python3", command="python3",
        about=("A general-purpose language for scripts, web apps, data and AI. Ubuntu ships it; this makes sure "
               "it's there."),
        site="https://www.python.org/downloads/"),
    App("pip", "Python packages", "Developer Tools", APT, "python3-pip", command="pip3",
        about=("Python's package installer, for the libraries on PyPI. Use it inside a virtual environment "
               "(python3 -m venv)."),
        site="https://pip.pypa.io/en/stable/installation/"),
    App("Java", "The Java development kit", "Developer Tools", APT, "default-jdk", command="java",
        version=("java", "-version"),
        about='OpenJDK: the compiler and runtime for Java programs, and what Maven, Gradle and Android builds need.',
        site="https://openjdk.org/install/"),
    App("Maven", "Java builds", "Developer Tools", APT, "maven", command="mvn",
        about="Builds Java projects and fetches their libraries, from the project's pom.xml.",
        site="https://maven.apache.org/install.html"),

    App("MySQL", "Database server", "Databases", APT, "mysql-server", command="mysqld",
        about='A database server: tables queried with SQL. Most PHP and Laravel apps use it.',
        site="https://dev.mysql.com/downloads/"),
    App("PostgreSQL", "Database server", "Databases", APT, "postgresql", command="psql",
        about='A database server with strict SQL, JSON columns and many extensions.',
        site="https://www.postgresql.org/download/linux/ubuntu/"),

    App("Brave", "Web browser that blocks ads", "Browsers", SNAP, "brave",
        also=((APT, "brave-browser"), (FLATPAK, "com.brave.Browser")),
        about='A Chromium-based browser that blocks ads and trackers by itself. Web Apps can run on it.',
        site="https://brave.com/linux/"),
    App("Chromium", "Open-source web browser; runs Web Apps", "Browsers", SNAP, "chromium",
        also=((APT, "chromium"), (FLATPAK, "org.chromium.Chromium")),
        about='The open-source browser Google Chrome is built on. Web Apps can run on it.',
        site="https://www.chromium.org/getting-involved/download-chromium/"),

    App("LibreOffice", "Documents, spreadsheets, slides", "Office", APT, "libreoffice",
        also=((SNAP, "libreoffice"), (FLATPAK, "org.libreoffice.LibreOffice")),
        about=("A free office suite: Writer for documents, Calc for spreadsheets, Impress for slides. Opens "
               "Microsoft Office files."),
        site="https://www.libreoffice.org/download/download-libreoffice/"),
    App("ONLYOFFICE", "Office suite that reads Microsoft formats", "Office", FLATPAK,
        "org.onlyoffice.desktopeditors",
        also=((SNAP, "onlyoffice-desktopeditors"), (APT, "onlyoffice-desktopeditors")),
        about=("An office suite that looks like Microsoft Office and keeps .docx, .xlsx and .pptx files closest to"
               " how Office shows them."),
        site="https://www.onlyoffice.com/download-desktop.aspx"),

    App("VLC", "Plays any video or audio", "Media", APT, "vlc", also=((SNAP, "vlc"), (FLATPAK, "org.videolan.VLC")),
        about='Plays almost any video or audio file, disc or stream, with no extra codecs to install.',
        site="https://www.videolan.org/vlc/download-ubuntu.html"),
    App("Spotify", "Music streaming", "Media", SNAP, "spotify",
        also=((FLATPAK, "com.spotify.Client"), (APT, "spotify-client")),
        about="Spotify's own app for music and podcasts.",
        site="https://www.spotify.com/download/linux/"),
    App("Kdenlive", "Video editor", "Media", FLATPAK, "org.kde.kdenlive", also=((APT, "kdenlive"), (SNAP, "kdenlive")),
        about='A video editor with a timeline, effects and transitions, from KDE.',
        site="https://kdenlive.org/en/download/"),
    App("Kooha", "Screen recorder", "Media", FLATPAK, "io.github.seadve.Kooha", also=((APT, "kooha"),),
        about='Records the screen, with sound if you want it, in a few clicks.',
        site="https://github.com/SeaDve/Kooha"),
    App("Pinta", "Paint program", "Media", FLATPAK, "com.github.PintaProject.Pinta",
        also=((SNAP, "pinta"), (APT, "pinta")),
        about=("A simple paint program, like Paint on Windows: draw, crop, resize and add text, with layers and "
               "effects when you want them."),
        site="https://www.pinta-project.com/releases/"),

    App("qBittorrent", "Torrent downloads", "Networking", APT, "qbittorrent",
        also=((FLATPAK, "org.qbittorrent.qBittorrent"),),
        about='Downloads torrents, with no ads, and a search across torrent sites.',
        site="https://www.qbittorrent.org/download"),
    App("LocalSend", "Send files to nearby devices", "Networking", FLATPAK, "org.localsend.localsend_app",
        also=((SNAP, "localsend"),),
        about='Sends files and text to phones and computers on the same Wi-Fi, with no account and no cable.',
        site="https://localsend.org/download"),
    App("RustDesk", "Remote desktop, open source", "Networking", FLATPAK, "com.rustdesk.RustDesk",
        about='Open-source remote desktop: control another computer, or let someone help on yours.',
        site="https://rustdesk.com/"),
    App("AnyDesk", "Remote desktop", "Networking", FLATPAK, "com.anydesk.Anydesk", also=((APT, "anydesk"),),
        about='Remote desktop: control another computer, or let someone help on yours.',
        site="https://anydesk.com/en/downloads/linux"),
    App("Cloudflare WARP", "The free 1.1.1.1 VPN", "Networking", APT, "cloudflare-warp", command="warp-cli",
        repo=("cloudflare-warp", "https://pkg.cloudflareclient.com/pubkey.gpg", "https://pkg.cloudflareclient.com/"),
        about=("Cloudflare's 1.1.1.1 app: encrypts your traffic and sends it through Cloudflare, free and with no "
               "account. It isn't in Ubuntu's packages, so Stitches adds Cloudflare's own repository first."),
        site="https://developers.cloudflare.com/warp-client/get-started/linux/",
        setup=("Register this computer, once: warp-cli registration new (answer y to the terms).",
               "Turn it on: warp-cli connect. Check it with warp-cli status.",
               "Turn it off: warp-cli disconnect.")),

    App("rclone", "Sync with cloud storage", "Utilities", APT, "rclone", command="rclone",
        version=("rclone", "version"),
        about='Copies and syncs files with Google Drive, OneDrive, Dropbox, S3 and dozens more, from the terminal.',
        site="https://rclone.org/install/"),
    App("Wine", "Runs Windows programs", "Utilities", APT, "wine", command="wine",
        about='Runs Windows programs on Linux without Windows.',
        site="https://gitlab.winehq.org/wine/wine/-/wikis/Debian-Ubuntu"),
    App("Luminance", "Brightness of external monitors", "Utilities", FLATPAK, "com.sidevesh.Luminance",
        about="Sets the brightness of external monitors, which the system's brightness slider usually can't.",
        site="https://github.com/sidevesh/Luminance"),
    App("Avro Phonetic", "Bangla typing", "Utilities", APT, "ibus-avro",
        about=('Type Bangla by spelling it in English letters: "ami" becomes আমি. The Avro Phonetic keyboard for '
               "IBus, the system's input method."),
        site="https://github.com/sarim/ibus-avro",
        setup=("Log out and back in (or run ibus restart in a terminal), so the system sees the new keyboard.",
               "Open Settings → Keyboard → Input Sources → Add Input Source…",
               "Search for Avro (it's under Bangla), pick Bangla (Avro Phonetic), then Add.",
               "Turn it on: press Super+Space, or click the language in the top bar, and pick Bangla. "
               "Type in English letters and Avro writes Bangla.",
               "Turn it off: Super+Space again, back to English.",
               "Remove it: Settings → Keyboard → ⋮ next to Bangla (Avro Phonetic) → Remove.")),
    App("Flatpak", "Installs Flatpak apps", "Utilities", APT, "flatpak", command="flatpak",
        about=("Installs apps from Flathub, each in a sandbox with its own libraries. App Manager adds it when a "
               "Flatpak app is picked."),
        site="https://flathub.org/setup/Ubuntu"),
)
