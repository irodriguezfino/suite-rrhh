# Actualizaciones automáticas

Suite RRHH consulta al abrirse el manifiesto público `updates/update-manifest.json`
del repositorio oficial. La consulta se realiza en segundo plano y no bloquea la
interfaz.

Cuando hay una versión superior, el usuario puede confirmar la instalación. El
actualizador incluido hace lo siguiente:

1. Cierra únicamente procesos `python.exe` y `pythonw.exe` cuyo comando apunta
   a la instalación de Suite RRHH del usuario actual.
2. Descarga el paquete HTTPS indicado por el manifiesto.
3. Comprueba su SHA-256 antes de extraerlo.
4. Sustituye de forma transaccional solo la carpeta `app`, conserva `runtime` y
   `config.json`, y vuelve a abrir la aplicación.

El paquete de actualización no contiene la configuración local ni la contraseña
de los libros Excel.

## Publicar una actualización

1. Incrementar `APP_VERSION` en `core/app_info.py`.
2. Ejecutar manualmente `crear_paquete_actualizacion.ps1 -Release`.
3. Subir `updates/update-manifest.json` y el ZIP generado al repositorio.
4. Para una instalación inicial nueva, crear también el instalador mediante
   `crear_release.ps1 -Release -ConfigPath .\release_config.local.json`.
