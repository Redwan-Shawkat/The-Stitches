# Wraps dist\TheUninstaller.exe in a Windows Installer package: Program Files,
# a Start Menu shortcut, and an Apps & Features entry — so the uninstaller is
# itself uninstallable the ordinary way, which felt like the minimum bar for
# this particular app. Run .\build-exe.ps1 first, or just .\build-all.ps1.
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

$exe = "$root\dist\TheUninstaller.exe"
if (-not (Test-Path $exe)) {
    throw "$exe not found. Run .\build-exe.ps1 first (or .\build-all.ps1)."
}

$version = (Select-String -Path "$root\pyproject.toml" -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value

# WiX ships as a .NET tool. Installed here rather than assumed, because a
# clean machine (and a clean CI runner) has neither.
if (-not (Get-Command wix -ErrorAction SilentlyContinue)) {
    dotnet tool install --global wix
    $env:PATH = "$env:PATH;$env:USERPROFILE\.dotnet\tools"
}

$msi = "$root\dist\TheUninstaller-$version-x64.msi"
wix build "$root\packaging\TheUninstaller.wxs" `
    -arch x64 `
    -d Version=$version `
    -d ExeSource=$exe `
    -d IconSource="$root\src\uninstaller\icon.ico" `
    -o $msi

Write-Host "Built $msi"
