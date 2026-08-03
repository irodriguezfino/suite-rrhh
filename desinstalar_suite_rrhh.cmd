@echo off
setlocal EnableExtensions
set "APP_DIR=%~dp0"

echo.
echo Se desinstalara Suite RRHH de este usuario.
choice /C SN /M "Deseas continuar"
if errorlevel 2 exit /b 0

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$w=New-Object -ComObject WScript.Shell; $desktop=[Environment]::GetFolderPath('Desktop'); $programs=[Environment]::GetFolderPath('Programs'); Remove-Item -LiteralPath (Join-Path $desktop 'Suite RRHH.lnk') -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath (Join-Path $programs 'Suite RRHH.lnk') -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath (Join-Path $programs 'Desinstalar Suite RRHH.lnk') -Force -ErrorAction SilentlyContinue"

start "" /b cmd.exe /c "timeout /t 2 /nobreak ^>nul ^& rmdir /s /q ""%APP_DIR%"""
exit /b 0
