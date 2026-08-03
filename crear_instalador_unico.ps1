param(
    [switch]$Release,
    [string]$ConfigPath
)

$ErrorActionPreference = 'Stop'

if (-not $Release) {
    throw "Este script genera un artefacto de distribución. Para una release manual usa: .\\crear_instalador_unico.ps1 -Release"
}

if (-not $ConfigPath) {
    $ConfigPath = $env:SUITE_RRHH_RELEASE_CONFIG
}
if (-not $ConfigPath -or -not (Test-Path -LiteralPath $ConfigPath)) {
    throw "Para generar una release indica -ConfigPath con un config.json local que contenga excel_password. Ese archivo no se publica en Git."
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$payload = Join-Path $projectRoot 'installer_payload'
$buildPayload = Join-Path ([System.IO.Path]::GetTempPath()) ("Suite_RRHH_Installer_" + [guid]::NewGuid().ToString('N'))
$appPayload = Join-Path $buildPayload 'app'
$runtimePayload = Join-Path $buildPayload 'runtime'
$uninstallPayload = Join-Path $buildPayload 'Desinstalar Suite RRHH.cmd'
$configPayload = Join-Path $buildPayload 'config.json'
$offlinePayload = Join-Path $buildPayload 'offline_payload.zip'
$bootstrapPayload = Join-Path $buildPayload 'bootstrap_payload.zip'
$outputDir = Join-Path $projectRoot 'entregable'
$outputFile = Join-Path $outputDir 'USB\Instalador_Universal_Suite_RRHH_20_20.exe'
$runtimeSource = Join-Path $env:TEMP 'RRHH_Installer_Build_Python311'
$runtimePython = Join-Path $runtimeSource 'python.exe'

foreach ($required in @(
    $runtimePython,
    (Join-Path $payload 'wheels\openpyxl-3.1.5-py2.py3-none-any.whl'),
    (Join-Path $payload 'wheels\pywin32-312-cp311-cp311-win_amd64.whl'),
    (Join-Path $payload 'wheels\pillow-12.3.0-cp311-cp311-win_amd64.whl'),
    (Join-Path $projectRoot 'requirements.txt'),
    (Join-Path $projectRoot 'instalar_rrhh.cmd'),
    (Join-Path $projectRoot 'desinstalar_suite_rrhh.cmd'),
    (Join-Path $projectRoot 'bootstrap_instalador.cs')
)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Falta el archivo requerido: $required"
    }
}

# El runtime es privado de la aplicacion: no se registra en Windows ni depende de un Python ya instalado.
# La interfaz utiliza Qt Widgets, incluido en Essentials. Addons (QML, Charts,
# WebEngine, etc.) no se usan y multiplican el tamaño del instalador USB.
& $runtimePython -m pip uninstall -y PySide6 PySide6_Addons | Out-Null
& $runtimePython -m pip install --force-reinstall --no-index --find-links (Join-Path $payload 'wheels') openpyxl pywin32 Pillow "PySide6_Essentials==6.11.1" "shiboken6==6.11.1"
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron preparar las librerias del entorno privado.' }
& $runtimePython -c "import openpyxl, PIL, win32com.client; from PySide6 import QtWidgets; print('RUNTIME_OK', QtWidgets.QApplication)"
if ($LASTEXITCODE -ne 0) { throw 'El entorno privado no supera la verificacion de librerias.' }

New-Item -ItemType Directory -Path $appPayload -Force | Out-Null
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null

foreach ($file in @('main.py', 'fase1_recopilacion.py', 'updater.py')) {
    Copy-Item -LiteralPath (Join-Path $projectRoot $file) -Destination $appPayload -Force
}
foreach ($directory in @('assets', 'core', 'services', 'workers', 'ui')) {
    Copy-Item -LiteralPath (Join-Path $projectRoot $directory) -Destination $appPayload -Recurse -Force
}
# PySide6 incluye recursos QML y de desarrollo con rutas que superan MAX_PATH
# dentro de OneDrive. La aplicación usa exclusivamente Qt Widgets, por lo que
# se excluyen esos recursos no ejecutables. Robocopy evita los fallos de
# Copy-Item al copiar árboles grandes de runtime.
$runtimeExclusions = @(
    (Join-Path $runtimeSource 'Lib\site-packages\PySide6\qml'),
    (Join-Path $runtimeSource 'Lib\site-packages\PySide6\include'),
    (Join-Path $runtimeSource 'Lib\site-packages\PySide6\examples'),
    (Join-Path $runtimeSource 'Lib\site-packages\PySide6\glue'),
    (Join-Path $runtimeSource 'Lib\idlelib'),
    (Join-Path $runtimeSource 'Lib\test'),
    (Join-Path $runtimeSource 'Lib\turtledemo'),
    (Join-Path $runtimeSource 'Tools')
)
$robocopyArgs = @($runtimeSource, $runtimePayload, '/E', '/R:5', '/W:2', '/NFL', '/NDL', '/NJH', '/NJS', '/NP', '/XD') + $runtimeExclusions
& robocopy @robocopyArgs
if ($LASTEXITCODE -ge 8) { throw "No se pudo copiar el runtime privado de PySide6. Robocopy=$LASTEXITCODE" }
Copy-Item -LiteralPath (Join-Path $projectRoot 'desinstalar_suite_rrhh.cmd') -Destination $uninstallPayload -Force
Copy-Item -LiteralPath $ConfigPath -Destination $configPayload -Force

# Validacion del runtime ya copiado, antes de incluirlo en el instalador.
& (Join-Path $runtimePayload 'python.exe') -c "import openpyxl, PIL, win32com.client; from PySide6 import QtWidgets; print('PAYLOAD_RUNTIME_OK', QtWidgets.QApplication)"
if ($LASTEXITCODE -ne 0) { throw 'El runtime empaquetado no funciona correctamente.' }

Remove-Item -LiteralPath $offlinePayload -Force -ErrorAction SilentlyContinue
Compress-Archive -Path $appPayload, $runtimePayload, $uninstallPayload, $configPayload -DestinationPath $offlinePayload -CompressionLevel Optimal

Remove-Item -LiteralPath $bootstrapPayload -Force -ErrorAction SilentlyContinue
Compress-Archive -Path @(
    (Join-Path $projectRoot 'instalar_rrhh.cmd'),
    $offlinePayload
) -DestinationPath $bootstrapPayload -CompressionLevel Optimal

Remove-Item -LiteralPath $outputFile -Force -ErrorAction SilentlyContinue
$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$references = @(
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\System.IO.Compression.dll'),
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\System.IO.Compression.FileSystem.dll'),
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\System.Windows.Forms.dll')
)
& $csc /nologo /target:winexe "/out:$outputFile" "/resource:$bootstrapPayload,SuiteRrhhInstaller.OfflinePayload.zip" ($references | ForEach-Object { "/reference:$_" }) (Join-Path $projectRoot 'bootstrap_instalador.cs')
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $outputFile)) {
    throw 'No se pudo generar el instalador unico.'
}

Get-Item -LiteralPath $outputFile | Select-Object FullName, Length, LastWriteTime
