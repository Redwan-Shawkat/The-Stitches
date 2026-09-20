# Both release artifacts plus their checksums, from a clean checkout.
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

& "$root\build-exe.ps1"
& "$root\build-msi.ps1"

Push-Location "$root\dist"
Get-FileHash *.exe, *.msi -Algorithm SHA256 |
    ForEach-Object { "$($_.Hash.ToLower())  $(Split-Path $_.Path -Leaf)" } |
    Set-Content -Encoding ascii SHA256SUMS.txt
Get-Content SHA256SUMS.txt
Pop-Location
