# Calificacion de noticias: diagnostico y hoja de ruta

Estado al 2026-10-03. Resume la evaluacion de Kev como calificador de
noticias, el diagnostico de las reglas con noticias reales, lo implementado
(seccion 3) y lo que queda abierto (seccion 4). Backlog general en
`NEXT_STEPS.md`.

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

## 2. Diagnostico inicial de las reglas

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

## 3. Implementado (2026-10-03)

### Resultados

Conjuntos etiquetados a mano en `tests/fixtures/` (relevante si/no y, si es
relevante, tema y region). Los evalua
`python -m scripts.evaluate_news_scoring [--file ...] [--details]`.

| Metrica | Desarrollo (160) antes | Desarrollo despues | Control (63) antes | Control 1a medicion | Control final |
|---|---|---|---|---|---|
| Precision del filtro | 0.82 | 0.91 | 0.47 | 0.58 | 0.75 |
| Recall del filtro | 0.57 | 0.91 | 0.39 | 0.78 | 0.83 |
| F1 | 0.68 | 0.91 | 0.42 | 0.67 | 0.79 |
| precision@10 del ranking | 1.00 | 1.00 | 0.50 | 0.60 | 0.80 |
| Tema correcto | 0.57 | 0.77 | 0.39 | 0.72 | 0.72 |
| Region correcta | 0.77 | 0.83 | 0.83 | 0.89 | 0.94 |

Como leer la tabla:

- **Desarrollo** (`news_eval.jsonl`, 28-29 sep): las reglas se ajustaron
  mirando este conjunto; sus numeros son optimistas.
- **Control** (`news_eval_holdout.jsonl`, 1-3 oct): etiquetado antes de
  correr las reglas. La **1a medicion** es la unica independiente. Despues
  se corrigieron errores vistos en el (fuentes oficiales, "Treasury
  Department", notas de carrera), asi que la columna final ya no lo es.
  Para la proxima medicion honesta hace falta un conjunto nuevo.
- Las etiquetas las puso Claude con criterio editorial ("¿la consideraria
  un editor del brief como candidata a titular?"); conviene que alguien del
  club las revise.

`tests/test_news_scoring_eval.py` fija pisos para que un cambio de reglas no
empeore la calificacion sin que nadie lo note.

### Cambios

1. **Tema por puntaje** (`classify_topic`): titular x3, resumen x1; empate
   por orden de `TOPIC_KEYWORDS` (macro antes que mercado, FX antes que
   commodities). Frases enmascaradas por tema: "tasa de desocupacion" no es
   "tasas"; "el fiscal", "terreno fiscal" o "fiscal year" no son politica
   fiscal. Vocabulario en espanol y bancos centrales nuevos.
2. **Filtro de calidad** (`news_quality.py`): palabras completas, sin el
   nombre de la fuente en el texto; los temas macro cuentan como senal.
   Fuentes oficiales tambien necesitan senal, sin contar su propio nombre.
   En fuentes tier 3 (MarketWatch, Investing.com) solo los temas de mercado
   (tasas, inflacion, bancos centrales, FX, commodities) bastan; empleo,
   actividad o fiscal necesitan un termino macro. Patrones de ruido nuevos:
   "...: Live levels", primera persona ("I'm 80", "my husband", "should I"),
   "price target", avisos de fondos, "comment period".
3. **Impacto** (`impact_scoring.py`): cobertura multi-fuente (+1 si otra
   fuente publica la misma historia, +2 si son dos o mas) en vez del +1 por
   tema; palabras completas; "Treasury Department" no activa el Treasury 10Y.
   Chile no estaba sin bono de region: la palabra clave "chile" calza con la
   etiqueta de region que se agrega al texto (+2), por eso no se toco.
4. **Deduplicacion**: indice por palabras (cada titulo se compara solo con
   los que comparten alguna) y `is_same_story` (Jaccard >= 0.5 de palabras
   significativas) para la cobertura multi-fuente.
5. **GET condicional** (`fetch_feed`): `If-None-Match`/`If-Modified-Since`
   con cache en memoria del proceso. Verificado en vivo: Fed, BCE, FT,
   MarketWatch e Investing.com responden 304; La Tercera ignora los
   validadores y DF no los envia.

6. **Diario Financiero** (`chile_news_client.py`): se lee la portada
   completa (~50 notas; antes se cortaba en 30), filtro por subseccion
   (entran Regiones y las subsecciones de economia y mercados de Senal DF) y
   etiquetas del feed (`df:tagnames`) para el tema. Con la portada del
   2026-10-03: de 8 a 36 notas y de 4 a 21 que pasan el filtro. Las
   etiquetas no se usan para la region: DF pone "Estados Unidos" en notas
   chilenas que solo lo mencionan. DF no publica feeds por seccion (404) y
   su sitemap trae URLs sin bajada, asi que el RSS de portada sigue siendo la
   fuente.

### Verificado y descartado

- **Resumen para Investing.com**: ninguno de sus feeds trae descripcion
  (probados `news.rss` y las secciones 1, 11, 14, 25 y 95). Se compenso
  filtrando mejor sus titulares.
- **Fuentes oficiales chilenas**: BCCh, CMF, INE y Hacienda no publican RSS
  (sus paginas de prensa no tienen enlaces de feed; la de BCCh no entrega
  contenido sin JavaScript). Sumarlas exige scraping de HTML; `AGENTS.md`
  pide preferir RSS. Los datos del BCCh (TPM, IPC, desempleo) ya llegan por
  su API.

## 4. Pendiente

1. **Conjunto de control nuevo**: etiquetar 50-100 notas de otra semana para
   medir sin sesgo, y que alguien del club revise las etiquetas existentes.
2. **Errores que quedan** (ver `--details`): IPO de Anthropic (empresa, no
   macro) rechazada; notas de MarketWatch con "inflation" en el resumen
   ("Switching jobs to get higher pay...") pasan; la region de medios
   chilenos que hablan de otros paises ("EEUU retira amenaza...") a veces
   queda mal. "China" como termino de alta senal deja pasar ensayos ("China,
   America and the new Great Game").
3. **Modelo como calificador (Kev o similar)**: no implementado porque no se
   pudo medir (sin GPU para Kev y sin `OLLAMA_API_KEY` en la maquina de
   desarrollo). Para probarlo: un modulo que haga las preguntas si/no,
   opcion y escala sobre los candidatos que pasan las reglas, correrlo sobre
   los dos conjuntos y activarlo solo si mejora `evaluate_news_scoring`. Si
   falla, `warning` y se usan las reglas. Nunca agrega notas.
4. **Monitor mas liviano** y frescura de fines de semana: siguen en
   `NEXT_STEPS.md`.
