# Flujo de desarrollo y release

## Desarrollo diario

Las comprobaciones ordinarias no deben crear instaladores, ejecutables de
distribucion ni paquetes ZIP.

Desde la raiz del proyecto:

```powershell
python -m unittest discover -s tests -v
python main.py
```

Tambien se puede utilizar el runtime privado existente para las pruebas cuando
no haya un Python global con las dependencias instaladas.

## Release del instalador universal

El instalador USB y el paquete de actualizacion se generan solo mediante una
accion manual explicita:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\crear_release.ps1 -Release -ConfigPath .\release_config.local.json
```

El archivo indicado por `-ConfigPath` debe contener la clave `excel_password`.
Es una configuracion local, esta excluida por `.gitignore` y no se publica.

El proceso prepara el runtime privado, valida las dependencias, crea el
instalador en `entregable\USB`, y genera en `updates\` el ZIP y manifiesto que
deben subirse al repositorio publico.

## Nueva version

1. Incrementar `APP_VERSION` en `core/app_info.py`.
2. Ejecutar pruebas.
3. Generar la release.
4. Publicar el ZIP y `update-manifest.json` junto con el codigo.
