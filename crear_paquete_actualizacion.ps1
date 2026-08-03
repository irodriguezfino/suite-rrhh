param(
    [switch]$Release
)

$ErrorActionPreference = 'Stop'
if (-not $Release) {
    throw "Este script genera el paquete de actualización. Para una release manual usa: .\\crear_paquete_actualizacion.ps1 -Release"
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$updates = Join-Path $projectRoot 'updates'
$staging = Join-Path ([System.IO.Path]::GetTempPath()) ("Suite_RRHH_Update_" + [guid]::NewGuid().ToString('N'))
$appStaging = Join-Path $staging 'app'
$versionLine = Select-String -LiteralPath (Join-Path $projectRoot 'core\app_info.py') -Pattern '^APP_VERSION\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $versionLine) { throw 'No se encontró APP_VERSION en core/app_info.py.' }
$version = $versionLine.Matches[0].Groups[1].Value
$packageName = "Suite_RRHH_update_$version.zip"
$packagePath = Join-Path $updates $packageName

function Copy-AppTree([string]$source, [string]$destination) {
    Get-ChildItem -LiteralPath $source -Recurse -File | Where-Object {
        $_.FullName -notmatch '\\__pycache__\\' -and $_.Extension -ne '.pyc'
    } | ForEach-Object {
        $relative = $_.FullName.Substring($source.Length).TrimStart('\')
        $target = Join-Path $destination $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        Copy-Item -LiteralPath $_.FullName -Destination $target -Force
    }
}

try {
    New-Item -ItemType Directory -Path $appStaging -Force | Out-Null
    foreach ($file in @('main.py', 'fase1_recopilacion.py', 'updater.py')) {
        Copy-Item -LiteralPath (Join-Path $projectRoot $file) -Destination $appStaging -Force
    }
    foreach ($directory in @('assets', 'core', 'services', 'workers', 'ui')) {
        Copy-AppTree (Join-Path $projectRoot $directory) (Join-Path $appStaging $directory)
    }
    New-Item -ItemType Directory -Path $updates -Force | Out-Null
    Remove-Item -LiteralPath $packagePath -Force -ErrorAction SilentlyContinue
    Compress-Archive -Path $appStaging -DestinationPath $packagePath -CompressionLevel Optimal
    $sha256 = (Get-FileHash -LiteralPath $packagePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $manifest = [ordered]@{
        version = $version
        package_url = "https://raw.githubusercontent.com/irodriguezfino/suite-rrhh/main/updates/$packageName"
        sha256 = $sha256
    } | ConvertTo-Json
    [System.IO.File]::WriteAllText(
        (Join-Path $updates 'update-manifest.json'),
        $manifest,
        (New-Object System.Text.UTF8Encoding($false))
    )
    Get-Item -LiteralPath $packagePath, (Join-Path $updates 'update-manifest.json') | Select-Object FullName, Length, LastWriteTime
}
finally {
    Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
}
