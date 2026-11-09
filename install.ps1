# PS3/PS4 Controller for the Wii Menu (4.3U) - installer for Windows
#
# Adds the "PS3/PS4 Controller" hack to Priiloader's hacks file on your Wii's
# SD card (apps\priiloader\hacks_hash.ini). Easiest way to run it:
# double-click install.bat in this folder, with the SD card plugged in.
#
# Or from PowerShell:
#   .\install.ps1                  (finds the SD card by itself)
#   .\install.ps1 E:\              (if it can't)
#   .\install.ps1 -Remove          (takes the hack back out)
#
# An older "PS3 Controller" entry is replaced, so there's never two.
#
# A backup of your hacks file is kept as hacks_hash.ini.before-ps3
param(
    [string]$SdPath = "",
    [switch]$Remove
)
$ErrorActionPreference = "Stop"

function Fail($msg) { Write-Host "[!] $msg" -ForegroundColor Red; exit 1 }

$hack = Join-Path $PSScriptRoot "ps3_ps4_controller.ini"
if (-not $Remove -and -not (Test-Path -LiteralPath $hack)) {
    Fail "ps3_ps4_controller.ini must be in the same folder as this script."
}

if ($SdPath -eq "") {
    $sysDrive = $env:SystemDrive.TrimEnd('\') + '\'
    $found = @(Get-PSDrive -PSProvider FileSystem |
        Where-Object { $_.Root -and $_.Root -ne $sysDrive -and (Test-Path -LiteralPath (Join-Path $_.Root "apps") -PathType Container) } |
        ForEach-Object { $_.Root })
    if ($found.Count -ne 1) {
        Fail ("Couldn't tell which drive is the SD card (found $($found.Count) with an apps folder).`n" +
              "    Run it again with the SD card's drive, for example:  .\install.ps1 E:\")
    }
    $SdPath = $found[0]
}
if (-not (Test-Path -LiteralPath (Join-Path $SdPath "apps") -PathType Container)) {
    Fail "$SdPath has no apps folder - is that the Wii's SD card?"
}
$dir = Join-Path (Join-Path $SdPath "apps") "priiloader"
$ini = Join-Path $dir "hacks_hash.ini"
Write-Host "SD card: $SdPath"
New-Item -ItemType Directory -Force -Path $dir | Out-Null

# Priiloader's standard hacks list (gzip + base64), used only when the SD card
# has no hacks_hash.ini yet. From the Priiloader project (GPL).
$stockB64 = @"
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
"@

# Write text with plain LF line endings and no byte-order mark
# (a BOM in front of the first [section] could confuse Priiloader).
$noBom = New-Object System.Text.UTF8Encoding($false)

if (-not (Test-Path -LiteralPath $ini)) {
    Write-Host "No hacks_hash.ini on the SD card yet: starting from Priiloader's standard list."
    $bytes = [Convert]::FromBase64String(($stockB64 -replace '\s', ''))
    $in = New-Object System.IO.MemoryStream(, $bytes)
    $gz = New-Object System.IO.Compression.GZipStream($in, [System.IO.Compression.CompressionMode]::Decompress)
    $out = New-Object System.IO.MemoryStream
    $gz.CopyTo($out)
    $gz.Dispose()
    [System.IO.File]::WriteAllBytes($ini, $out.ToArray())
}
if (-not (Test-Path -LiteralPath "$ini.before-ps3")) { Copy-Item -LiteralPath $ini -Destination "$ini.before-ps3" }

# Take out any older copy of the hack and all blank lines (Priiloader stops
# reading at a blank line).
$lines = New-Object System.Collections.Generic.List[string]
$skip = $false
foreach ($line in [System.IO.File]::ReadAllLines($ini)) {
    $line = $line.TrimStart([char]0xFEFF).TrimEnd("`r")
    if ($line -match '^\[PS3( |/PS4 )Controller') { $skip = $true; continue }
    if ($line -match '^\[') { $skip = $false }
    if ($skip) { continue }
    if ($line -match '^\s*$') { continue }
    $lines.Add($line)
}

if (-not $Remove) {
    foreach ($line in [System.IO.File]::ReadAllLines($hack)) {
        $line = $line.TrimStart([char]0xFEFF).TrimEnd("`r")
        if ($line -match '^\s*$') { continue }
        $lines.Add($line)
    }
}
[System.IO.File]::WriteAllText($ini, (($lines -join "`n") + "`n"), $noBom)

$n = @($lines | Where-Object { $_ -match '^\[' }).Count
$name = ([System.IO.File]::ReadAllLines($hack)[0]).TrimStart([char]0xFEFF).Trim().Trim('[', ']')
if ($Remove) {
    $ps3 = @($lines | Where-Object { $_ -match '^\[PS3( |/PS4 )Controller' }).Count
} else {
    $ps3 = @($lines | Where-Object { $_ -eq "[$name]" }).Count
}
if ($Remove) {
    if ($ps3 -ne 0) { Fail "Removing didn't work." }
    Write-Host "Removed. The hacks file now lists $n hacks."
    Write-Host "Backup of the original: $ini.before-ps3"
    Write-Host "Now safely eject the SD card."
} else {
    if ($ps3 -ne 1) { Fail "Adding didn't work." }
    Write-Host "Added `"$name`" as the last of $n hacks." -ForegroundColor Green
    Write-Host "Backup of the original: $ini.before-ps3"
    Write-Host "Now safely eject the SD card, then turn on `"$name`" in Priiloader's System Menu Hacks (and save settings)."
}
