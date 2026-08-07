param(
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$distDirectory = Join-Path $projectRoot "dist\VoiceGun"
$executable = Join-Path $distDirectory "VoiceGun.exe"
$releaseDirectory = Join-Path $projectRoot "release"

if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    throw "VoiceGun.exe not found. Run build_windows.bat first."
}

$versionFile = Join-Path $projectRoot "gpt01\version.py"
$versionMatch = Select-String -LiteralPath $versionFile -Pattern '^__version__ = "([^"]+)"$'
if (-not $versionMatch) {
    throw "Application version was not found in gpt01/version.py."
}
$version = $versionMatch.Matches[0].Groups[1].Value

foreach ($document in @("LICENSE", "README.md", "DISTRIBUTION.md", "Doc-Size.md")) {
    $source = Join-Path $projectRoot $document
    if (Test-Path -LiteralPath $source -PathType Leaf) {
        Copy-Item -LiteralPath $source -Destination $distDirectory -Force
    }
}

New-Item -ItemType Directory -Path $releaseDirectory -Force | Out-Null
$archiveName = "VoiceGun-$version-windows-x64.zip"
$archivePath = Join-Path $releaseDirectory $archiveName
$checksumPath = "$archivePath.sha256"

if (Test-Path -LiteralPath $archivePath) {
    Remove-Item -LiteralPath $archivePath -Force
}
if (Test-Path -LiteralPath $checksumPath) {
    Remove-Item -LiteralPath $checksumPath -Force
}

Compress-Archive -LiteralPath $distDirectory -DestinationPath $archivePath `
    -CompressionLevel Optimal

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($archivePath)
try {
    $requiredEntries = @("VoiceGun/VoiceGun.exe", "VoiceGun/_internal/")
    $entryNames = $zip.Entries.FullName -replace '\\', '/'
    foreach ($requiredEntry in $requiredEntries) {
        if (-not ($entryNames | Where-Object { $_.StartsWith($requiredEntry) })) {
            throw "Required archive entry is missing: $requiredEntry"
        }
    }
}
finally {
    $zip.Dispose()
}

$hash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  $archiveName" | Set-Content -LiteralPath $checksumPath -Encoding ascii

$archive = Get-Item -LiteralPath $archivePath
Write-Output "Package: $($archive.FullName)"
Write-Output "Size MB: $([math]::Round($archive.Length / 1MB, 1))"
Write-Output "SHA-256: $hash"
