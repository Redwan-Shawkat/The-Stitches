# Builds dist\TheUninstaller.exe — one portable file, no install, no Python
# on the target machine. Run from anywhere:  .\build-exe.ps1
#
# PyInstaller is the only build-time dependency in the whole project; the app
# itself still imports nothing outside the standard library.
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

python -m pip install --upgrade --disable-pip-version-check --quiet pyinstaller

python -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name TheUninstaller `
    --icon "$root\src\uninstaller\icon.ico" `
    --add-data "$root\src\uninstaller\icon.ico;uninstaller" `
    --paths "$root\src" `
    --distpath "$root\dist" --workpath "$root\build" --specpath "$root\build" `
    "$root\run.py"

Write-Host "Built $root\dist\TheUninstaller.exe"
