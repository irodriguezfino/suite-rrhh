# Comparaciones compartidas — desde 1.0.22

## Uso

1. Generar la comparación con los dos Excel como siempre.
2. En el resultado: **Compartir → Exportar comparación completa**.
3. Guardar el `.rrhh` y enviarlo solo a destinatarios autorizados.
4. El destinatario abre el comparador y pulsa **Importar comparación**, o arrastra
   el archivo a la página. No necesita los Excel originales para revisar.

Se exporta todo el resultado, nunca solo las filas visibles por los filtros.
La tabla continúa siendo de solo lectura. Se conservan filtros, recuentos,
valores originales para el detalle, diferencias, motivos y explicaciones.
Los dos informes existentes se incluyen como copias exactas y pueden guardarse
desde la comparación importada. No se ejecutan Excel ni el motor de comparación
durante la importación. No se corrigen horas ni se guardan anotaciones.

Ambos equipos necesitan Suite RRHH 1.0.22 o posterior para abrir `.rrhh`.
Las versiones 1.0.21 y anteriores no incorporan esta función.

## Privacidad y fiabilidad

El archivo contiene nombres, códigos, horas e incidencias; **no está cifrado**.
No incluye los libros originales ni las rutas del registro técnico. Las sumas
SHA-256 detectan daños, pero no autentican al remitente ni impiden que alguien
con conocimientos modifique el archivo y regenere sus sumas.

El formato 1 contiene exactamente `manifest.json`, `result.json`, `resultado.xlsx`
e `incidencias.xlsx`. Es ZIP + JSON; nunca pickle ni código ejecutable. El lector
limita tamaño comprimido/descomprimido (40 MB), número de filas (20.000), registros
de auditoría (200.000), textos, tipos numéricos y nombres de miembros. No extrae
rutas recibidas. Rechaza versiones desconocidas y reportes con macros/objetos
incrustados o enlaces externos de Excel. No abre informes automáticamente.

La escritura es atómica. Si falla una importación, la vista anterior permanece.
Si falla una exportación, no se sustituye el archivo anterior. Los tiempos se
guardan como minutos enteros. Las explicaciones y resúmenes del detalle se guardan
como texto para no reinterpretar resultados antiguos con nuevas reglas.

Al evolucionar el formato, incrementar su versión y añadir migraciones explícitas
y pruebas de compatibilidad; nunca completar datos ausentes suponiendo ceros.
