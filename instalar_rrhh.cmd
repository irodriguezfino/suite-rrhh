@echo off
setlocal EnableExtensions
title Instalador Universal Suite RRHH

set "APP_NAME=Suite RRHH"
set "BASE_DIR=%LOCALAPPDATA%\Programs\Suite RRHH"
set "PYTHONW_EXE=%BASE_DIR%\runtime\pythonw.exe"
set "LAUNCHER_VBS=%BASE_DIR%\Iniciar Suite RRHH.vbs"
set "UNINSTALLER=%BASE_DIR%\Desinstalar Suite RRHH.cmd"
set "CONFIG_FILE=%BASE_DIR%\config.json"

echo.
echo ================================================================
echo             INSTALADOR UNIVERSAL - SUITE RRHH
echo ================================================================
echo.
echo Antes de continuar, cierra cualquier ventana de Suite RRHH.
echo.
pause

echo.
echo [1/5] Desinstalando todas las versiones anteriores...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$w=New-Object -ComObject WScript.Shell; $desktop=[Environment]::GetFolderPath('Desktop'); $programs=[Environment]::GetFolderPath('Programs'); Remove-Item -LiteralPath (Join-Path $desktop 'Suite RRHH.lnk') -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath (Join-Path $programs 'Suite RRHH.lnk') -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath (Join-Path $programs 'Desinstalar Suite RRHH.lnk') -Force -ErrorAction SilentlyContinue"
if exist "%BASE_DIR%" rmdir /S /Q "%BASE_DIR%" 2>nul
if exist "%BASE_DIR%" goto :old_versions_locked

echo [2/5] Preparando la nueva instalacion...
mkdir "%BASE_DIR%"
if errorlevel 1 goto :error

echo [3/5] Instalando Python, librerias y dependencias incluidas...
echo       (Python, PySide6 Qt Widgets, OpenPyXL, Pillow y PyWin32)
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath '%~dp0offline_payload.zip' -DestinationPath '%BASE_DIR%'"
if errorlevel 1 goto :extract_error
if not exist "%PYTHONW_EXE%" goto :runtime_error
if not exist "%UNINSTALLER%" goto :uninstall_error
if not exist "%CONFIG_FILE%" goto :config_error

echo [4/5] Configurando el programa y los accesos directos...
> "%LAUNCHER_VBS%" echo Set shell = CreateObject("WScript.Shell"^)
>> "%LAUNCHER_VBS%" echo launchCommand = Chr(34) ^& "%PYTHONW_EXE%" ^& Chr(34) ^& " " ^& Chr(34) ^& "%BASE_DIR%\app\main.py" ^& Chr(34)
>> "%LAUNCHER_VBS%" echo shell.Run launchCommand, 0, False

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$w=New-Object -ComObject WScript.Shell; $desktop=[Environment]::GetFolderPath('Desktop'); $programs=[Environment]::GetFolderPath('Programs'); $icon='%BASE_DIR%\app\assets\ICONO_SUITE_RRHH.ico'; $argument=([char]34)+'%LAUNCHER_VBS%'+([char]34); $start=$w.CreateShortcut((Join-Path $programs 'Suite RRHH.lnk')); $start.TargetPath=$env:WINDIR+'\System32\wscript.exe'; $start.Arguments=$argument; $start.WorkingDirectory='%BASE_DIR%\app'; $start.IconLocation=$icon; $start.Save(); $desk=$w.CreateShortcut((Join-Path $desktop 'Suite RRHH.lnk')); $desk.TargetPath=$env:WINDIR+'\System32\wscript.exe'; $desk.Arguments=$argument; $desk.WorkingDirectory='%BASE_DIR%\app'; $desk.IconLocation=$icon; $desk.Save(); $uninstall=$w.CreateShortcut((Join-Path $programs 'Desinstalar Suite RRHH.lnk')); $uninstall.TargetPath='%UNINSTALLER%'; $uninstall.WorkingDirectory='%BASE_DIR%'; $uninstall.IconLocation=$icon; $uninstall.Save()"
if errorlevel 1 goto :shortcut_error

echo.
echo [5/5] Instalacion terminada correctamente.
echo Se han creado accesos directos en el Escritorio y el menu Inicio.
start "" "%LAUNCHER_VBS%"
echo.
echo Revisa los mensajes anteriores y presiona una tecla para cerrar esta ventana.
pause >nul
exit /b 0

:old_versions_locked
echo.
echo ERROR: No se han podido eliminar todas las versiones anteriores.
echo Cierra por completo Suite RRHH y vuelve a ejecutar este instalador.
goto :finish_error

:extract_error
echo.
echo ERROR: No se pudieron extraer los recursos incluidos.
goto :finish_error

:runtime_error
echo.
echo ERROR: El entorno incluido de la aplicacion no se ha copiado correctamente.
goto :finish_error

:uninstall_error
echo.
echo ERROR: No se pudo preparar el desinstalador.
goto :finish_error

:config_error
echo.
echo ERROR: No se pudo instalar la configuracion local requerida.
goto :finish_error

:shortcut_error
echo.
echo ERROR: La aplicacion se instalo, pero no se pudieron crear los accesos directos.
goto :finish_error

:error
echo.
echo ERROR: No se pudo preparar la carpeta de instalacion.

:finish_error
echo.
echo La instalacion no se ha completado. Revisa el mensaje anterior.
pause
exit /b 1
