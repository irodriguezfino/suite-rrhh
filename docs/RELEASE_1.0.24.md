# Suite RRHH 1.0.24

## Ordenación en la vista del informe

Pulsa una cabecera para ordenar de menor a mayor y vuelve a pulsarla para
invertir el sentido. Se aplica a toda la vista filtrada, también entre secciones.
Las duraciones se comparan como minutos con signo, no como texto. Los guiones
quedan al final en ambos sentidos. Los empates mantienen sección y apellidos.
Vista permite ordenar por teclado y restablecer sección/apellidos.

## Tolerancia en minutos

El filtro de Tolerancia afecta solo a la vista. Con 5 min, los valores entre
−5 y +5 inclusive no justifican mantener una fila por diferencias ordinarias.
Otra diferencia superior al margen sí la mantiene. Al elegir un motivo,
la tolerancia se aplica a ese concepto. Los avisos rojos (incluido ABSENT),
fichajes pendientes, personas sin correspondencia y secciones por verificar
siguen sus reglas especiales. Los valores mostrados no se sustituyen por ceros.

Sin filtro (0) y Quitar filtros recuperan el resultado original. Una comparación
nueva/importada empieza sin tolerancia adicional y con sección/apellidos.
El filtro no recupera trabajadores descartados durante el cálculo original.

Los Excel y .rrhh conservan todos los datos originales: ordenar y filtrar no
recalcula ni modifica informes. Compatible con las comparaciones .rrhh existentes.
