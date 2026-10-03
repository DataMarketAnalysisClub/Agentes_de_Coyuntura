# Calificacion de noticias: diagnostico y hoja de ruta

Estado al 2026-10-03. Resume la evaluacion de Kev como calificador de
noticias, mide como se comportan las reglas actuales con noticias reales y
propone por donde avanzar. Backlog general en `NEXT_STEPS.md`.

## 1. Kev (descartado por ahora)

[Kev](https://github.com/jaredpalmer/kev) (Apache-2.0, v1.0) es una familia
de modelos pequenos (Qwen + LoRA) que leen un texto una vez y responden
varias preguntas sobre el con probabilidades calibradas:

| Tipo | Respuesta | Uso posible en el brief |
|---|---|---|
| `noul` (si/no) | probabilidad de "si" | "¿Mueve mercados?", "¿Es finanzas personales o promocion?" |
| `choice` | opcion + probabilidades | tema y region |
| `score` | nivel + confianza | impacto de mercado 1-5 |

API: `POST /v1/systemone` con `state` (el texto) y `questions`. Se puede
ajustar con datos propios (`kev.train --init_from`).

**Por que no ahora:**

- Requiere GPU (CUDA, ROCm o Apple Silicon/MLX): Kev-0.8B ~4 GB de VRAM,
  Kev-4B ~8.4 GB. Sin soporte documentado para CPU, GGUF ni Ollama.
- El equipo de desarrollo (Intel Iris Xe) no sirve; la IA de produccion usa
  Ollama Cloud (`gpt-oss:120b`), no un modelo local, y no esta confirmado que
  `nixbox` tenga GPU.
- Entrenado sobre todo en ingles y en textos de <= 384 tokens. Los titulares
  caben, pero el desempeno en las notas de La Tercera y DF (espanol) no esta
  medido.

**Cuando reconsiderarlo:** si se dispone de una GPU (servidor nuevo junto con
el dominio y la pagina web, o GPU por horas). El esquema de preguntas
(si/no, opcion, escala) es reutilizable: se puede probar primero con el
modelo de Ollama Cloud que ya se usa, sin calibracion, y cambiar el backend
despues. La IA seguiria solo calificando candidatos; nunca agregando notas.

## 2. Diagnostico de las reglas actuales

Medido sobre las 160 notas de `storage/dmac_market_brief.db` local
(2026-09-28 19:38 a 2026-09-29 17:52 UTC). Es un solo dia: los numeros son
indicativos, no una evaluacion.

| Medida | Valor |
|---|---|
| Notas por fuente | Investing.com 66, DF 34, MarketWatch 23, La Tercera 21, FT 15, ECB 1 |
| Tema "macro general" (sin tema) | 81 de 160 (51%) |
| Region "Global" | 112 de 160 (70%) |
| Rechazadas por `low_macro_relevance` | 122 de 160 (76%) |
| Pasan el filtro de calidad | 33 de 160 |
| Sin resumen | 69 (las 66 de Investing.com, 2 de DF, 1 del ECB) |
| `count_similar_headlines > 0` | 159 de 160 |

### Hallazgos

1. **El tema se decide por la primera coincidencia** (`classify_topic`
   recorre `TOPIC_KEYWORDS` en orden y "tasas" va primero). Ejemplos reales:
   - "Expertos aprueban plan laboral, pero piden un subsidio al empleo" -> tasas
   - "Ministro Daniel Mas ... gasto publico del Presupuesto 2027" -> tasas
     (deberia ser politica fiscal)
   - "Dolar anota mayor valor en mas de un ano" -> commodities (deberia ser FX)
   - "Bolsa chilena repunta ..." -> FX (deberia ser renta variable)
   - "Santander reduce ... proyeccion de crecimiento de Chile" -> inflacion
   Como el cupo de titulares es por tema (`per_topic_limit`), un tema mal
   asignado tambien cambia que notas compiten entre si.

2. **Sesgo contra notas chilenas en el filtro de calidad.**
   `HIGH_SIGNAL_TERMS` tiene poco vocabulario en espanol (no incluye
   "empleo", "desempleo", "presupuesto", "fiscal", "crecimiento", "bolsa",
   "ipsa", "ipc", "pib"). Rechazadas por `low_macro_relevance`:
   - "Gobierno anuncia plan laboral que movilizara recursos por unos
     US$1.350 millones" (tema empleo)
   - "Lula y Flavio Bolsonaro empatan en las encuestas ..." (eleccion en
     Brasil; ademas "Lula"/"Bolsonaro" no marcan region Latam)

3. **Ruido que si pasa el filtro:**
   - Finanzas personales: "'I have a low interest rate': I'm 80 years old.
     Should I move out of my house ..." (MarketWatch), calidad 7, impacto 8.
   - Analisis tecnico de Investing.com: "S&P 500 wedged at 7,739 between key
     support and resistance: Live", "Dollar Index battles 101.49 double top
     resistance: Live levels".

4. **Senal muerta en el impacto.** `count_similar_headlines` cuenta una nota
   como "similar" si comparte el tema, asi que 159 de 160 suman +1. La senal
   util seria la cobertura real: cuantas fuentes distintas publican la misma
   historia.

5. **El impacto se satura.** 12 notas tienen impacto 10 (el tope) y 77
   tienen 2; el desempate termina dependiendo de la hora.

6. **Investing.com domina el volumen sin resumen.** 41% de las notas, todas
   calificadas solo por el titulo.

7. **Substring en `news_quality.py` e `impact_scoring.py`.** Ya estaba en el
   backlog. En esta muestra no produjo falsos positivos visibles, y el nombre
   de la fuente no decidio ninguna nota. Conviene igual pasar a la busqueda
   por palabra completa de `news_classifier.py` para no depender de la
   suerte ("fed" calza con "fedex", "oil" con "turmoil", "tech" con
   "fintech").

## 3. Hoja de ruta propuesta

Ordenada por impacto/esfuerzo. Todo deterministico, con tests de regresion
por cada ejemplo real citado arriba.

### Fase 1: corregir las reglas (sin dependencias nuevas)

1. **Tema por puntaje, no por orden:** contar coincidencias por tema,
   ponderando el titulo sobre el resumen (como `select_news_charts`), y
   desempatar por especificidad.
2. **Vocabulario en espanol y una sola fuente de verdad:** que
   "alta senal" se derive de los temas detectados (tema distinto de
   "macro general") en vez de una lista paralela; agregar los terminos que
   faltan y Lula/Bolsonaro/Milei/Sheinbaum... a Latam.
3. **Patrones de bajo valor nuevos:** analisis tecnico ("live levels",
   "support and resistance", "52-week low") y finanzas personales en primera
   persona ("i'm NN years old", "should i").
4. **Cobertura multi-fuente** en lugar del +1 por tema: +1 si otra fuente
   publica una nota similar, +2 si son dos o mas.
5. **Busqueda por palabra completa** en `news_quality.py` e
   `impact_scoring.py`, reutilizando `_compile_keywords`.

### Fase 2: conjunto de evaluacion

Sin un conjunto etiquetado no se puede saber si un cambio mejora o empeora.

- Exportar unas 200-300 notas reales (idealmente de la SQLite de produccion,
  que tiene varias semanas) y etiquetarlas a mano: relevante si/no, tema,
  region.
- Script `scripts/evaluate_news_scoring.py` que reporte precision/recall del
  filtro y exactitud de tema/region. Correrlo antes y despues de cada cambio.
- El mismo conjunto sirve para comparar despues Kev u otro modelo.

### Fase 3: scraping

1. **Resumen para Investing.com:** el feed no trae descripcion. Evaluar
   feeds por seccion de Investing.com o bajar su peso.
2. **GET condicional** (`ETag`/`Last-Modified`), ya en el backlog.
3. **Fuentes oficiales chilenas:** comunicados del BCCh, CMF, INE y Hacienda
   (hoy aparecen en `SOURCE_TIERS` pero no hay feed). Verificar si publican
   RSS antes de comprometerse.
4. **Deduplicacion por tokens** en vez de `SequenceMatcher` O(n^2); tambien
   habilita la senal de cobertura multi-fuente.

### Fase 4: modelo como calificador (opcional)

Con el conjunto de evaluacion listo, probar el esquema de preguntas de Kev
sobre los candidatos que pasan las reglas, primero con Ollama Cloud. Solo se
activa si mejora la evaluacion; si falla, `warning` y se usan las reglas.
