Suite RRHH - Control Tempo
==========================

Aplicacion de escritorio para recopilar partes de trabajo diarios o mensuales
en Excel. La interfaz esta construida con PySide6 y el motor conserva la
compatibilidad con los libros de entrada y salida existentes.

Ejecucion de desarrollo:
    python main.py

Pruebas:
    python -m unittest discover -s tests -v

Instalador y actualizaciones
----------------------------

El instalador universal se crea de forma manual y no requiere Inno Setup ni un
Python instalado en el equipo de destino. Para generar una release se necesita
un archivo local, no versionado, que contenga la clave Excel:

    powershell -NoProfile -ExecutionPolicy Bypass -File .\crear_release.ps1 -Release -ConfigPath .\release_config.local.json

El instalador se genera en `entregable\USB`. El paquete de actualizacion y su
manifiesto se generan en `updates\` y se publican en GitHub. Al abrir una copia
instalada, Suite RRHH consulta el manifiesto en segundo plano y pide
confirmacion antes de actualizar.

Estructura
----------

    main.py                        Punto de entrada PySide6.
    ui/                            Interfaz grafica.
    workers/                       Trabajos fuera del hilo de interfaz.
    services/                      Servicios de aplicacion y actualizaciones.
    core/                          Configuracion y datos de version.
    fase1_recopilacion.py          Motor de procesamiento Excel.
    updater.py                     Actualizador independiente.
    assets/                        Logos e icono usado por la aplicacion.
    crear_release.ps1              Generador de instalador y actualizaciones.
    updates/                       Paquete y manifiesto del canal publico.
    docs/                          Documentacion de release y actualizaciones.

Notas
-----

- La clave de proteccion de Excel nunca se publica: se lee de `config.json`
  dentro de cada instalacion o de la variable `SUITE_RRHH_EXCEL_PASSWORD`.
- Microsoft Excel debe estar instalado en los equipos que procesen libros.
- La salida contiene las hojas Recopilacion, Auditoria y Trabajadores Auditoria.
