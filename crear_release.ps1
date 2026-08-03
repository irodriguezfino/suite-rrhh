param(
    [switch]$Release,
    [string]$ConfigPath
)

$ErrorActionPreference = 'Stop'
if (-not $Release) {
    throw "La release es manual. Usa: .\\crear_release.ps1 -Release -ConfigPath C:\\ruta\\config.json"
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $root 'crear_paquete_actualizacion.ps1') -Release
& (Join-Path $root 'crear_instalador_unico.ps1') -Release -ConfigPath $ConfigPath
