@echo off
setlocal EnableExtensions
title Suite RRHH - Prueba local

cd /d "%~dp0"
set "RUNTIME=%LOCALAPPDATA%\Programs\Suite RRHH\runtime\python.exe"

echo.
echo ================================================================
echo              SUITE RRHH - PRUEBA LOCAL
echo ================================================================
echo Carpeta de codigo: %CD%
echo.

if not exist "%RUNTIME%" (
    echo ERROR: No se encontro el runtime instalado de Suite RRHH:
    echo %RUNTIME%
    echo.
    echo Ejecuta primero la instalacion normal de Suite RRHH o avisa de este mensaje.
    pause
    exit /b 1
)

echo Iniciando la version local con diagnostico visible...
echo Cierra la ventana de Suite RRHH para volver a esta consola.
echo.
"%RUNTIME%" -X faulthandler -u main.py
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%EXIT_CODE%"=="0" (
    echo ERROR: La prueba local termino con codigo %EXIT_CODE%.
    echo Copia todo este mensaje y compartelo para revisarlo.
) else (
    echo La prueba local se cerro correctamente.
)
echo.
pause
exit /b %EXIT_CODE%
