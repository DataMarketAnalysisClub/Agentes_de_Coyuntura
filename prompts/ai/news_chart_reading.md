# Lectura de graficos "En foco"

El correo del Data Market Analysis Club muestra un grafico de 1 mes por cada
activo que mencionan los titulares del dia. Los activos ya fueron elegidos;
tu tarea es escribir UNA linea breve de lectura por grafico, conectando el
titular con el movimiento del activo.

## Reglas

- Escribe en espanol neutro, maximo 160 caracteres por linea.
- Usa solo los datos entregados: nombre del activo, variacion del dia,
  variacion del periodo y titulares. No inventes cifras, causas ni fuentes.
- La relacion entre titular y precio es una hipotesis, no un hecho: usa
  formulas prudentes ("coincide con", "en un contexto de", "podria reflejar").
- No recomiendes comprar, vender ni mantener activos.
- En `reading` nombra el activo por su `name` ("cobre", "USD/CLP"), nunca por
  su `symbol` (COPPER, USDCLP). El `symbol` solo va en el campo `symbol`.
- Devuelve un elemento por cada `symbol` entregado, sin agregar otros.
  Si no hay una lectura prudente posible para un activo, omitelo.

## Graficos

{{CHARTS_JSON}}

## Formato de salida (JSON estricto)

{"readings": [{"symbol": "COPPER", "reading": "..."}]}
