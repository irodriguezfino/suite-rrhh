# Suite RRHH 1.0.25

## Tolerancia fácil de introducir

El campo empieza en **0:00** (sin tolerancia adicional) y selecciona su contenido
al recibir el foco. Escribe **0:05** para cinco minutos o **1:30** para noventa.
Admite duraciones superiores a 24 horas y minutos sueltos (5 se normaliza a 0:05).
El filtro se aplica tras una pausa de 350 ms, o inmediatamente con Intro o al
salir del campo. Los formatos no válidos no cambian el filtro; el aviso accesible
del campo indica el formato correcto y la última tolerancia aplicada.

Se corrige la pérdida de foco cuando el filtro deja la tabla vacía, para poder
seguir escribiendo y recuperar los resultados sin volver a pulsar el campo.

## Selección de varias secciones

Abre Sección y marca las casillas de las secciones deseadas. El desplegable
permanece abierto para seguir seleccionando. Espacio marca/desmarca; Esc cierra.
Se muestran las filas de cualquiera de las secciones marcadas, sin duplicados.
Todas las secciones, o desmarcar la última selección, recupera todas las filas.
Los recuentos de origen suman las secciones seleccionadas, antes de los demás
filtros. Si se incluye Solo en un origen no se presenta una suma por sección
que pudiera resultar engañosa. Las secciones sin datos de recuento se indican.

La selección se combina con tolerancia, motivo, incidencia, búsqueda y orden.
Quitar filtros y una comparación nueva/importada restablecen ambas opciones.
Ayuda y novedades actualizadas. Los cálculos, Excel e intercambios .rrhh no
cambian: los filtros afectan únicamente a la vista, conservando los avisos
especiales existentes. Compartir sigue exportando el resultado completo.
