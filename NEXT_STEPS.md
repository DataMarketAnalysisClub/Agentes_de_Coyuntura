# Siguientes Pasos

Estado a v0.14.0 (2026-09-28). Reemplaza la version anterior de este archivo
(escrita en v0.2.0), cuyas opciones A-D quedaron implementadas o superadas.

## Estado de fuentes (medido en vivo el 2026-09-28)

| Fuente | Tipo | Estado |
|--------|------|--------|
| BCCh API | Datos (TPM, IPC) | Funcional (requiere credenciales) |
| yfinance 1.7.0 | Datos de mercado + series 1 mes | 17/18 en ~2.5s; IPSA via `MXIPSAGC.SN`; USD/PEN descartado por datos inconsistentes |
| Federal Reserve | RSS | 20 notas |
| ECB | RSS | 15 notas |
| Financial Times | RSS | 12 notas |
| MarketWatch | RSS | 10 notas |
| Investing.com | RSS | 10 notas (fecha no RFC 822, ya soportada) |
| La Tercera Pulso | RSS oficial + respaldo HTML | 20 notas con fecha real |

Descarga de RSS: ~2.9s en serie -> ~0.7s en paralelo (0.24s con conexiones
reutilizadas). Detalle en `CHANGELOG.md` (0.14.0).

---

## yfinance y graficos: estado y pendientes

Reparado en 0.14.0 (detalle en `CHANGELOG.md`): una descarga batch de 1 mes
entrega cotizacion + serie; IPSA vuelve via `MXIPSAGC.SN` (velas horarias);
series inconsistentes o vencidas se descartan; version fijada a 1.7.0; y la
tabla de activos del correo muestra una sparkline de 1 mes en HTML/CSS.

### Por que sparklines HTML y no imagenes

Las imagenes embebidas (cid: y base64) ya fallaron en Outlook mobile/web
(`docs/email-output.md`), y Gmail no muestra imagenes `data:`. Las barras con
`border-bottom` en celdas de tabla se ven en todos los clientes, cuestan
~1.3 KB por activo y no agregan dependencias.

### Pendientes

1. **USD/PEN.** `PEN=X`, `USDPEN=X` y `PENUSD=X` traen las mismas velas
   inconsistentes (16 de 23). Hoy se muestra "s/d". Opciones: otra fuente
   (BCRP publica el tipo de cambio oficial), o sacarlo de `DEFAULT_ASSETS`.
2. **IPSA via proxy de Yahoo.** `MXIPSAGC.SN` coincide con el S&P IPSA, pero
   Yahoo lo rotula "MSCI IPSA INDEX (con dividendos)" y su historial solo
   parte en sep-2026. Si el BCCh publica una serie del IPSA, seria la fuente
   oficial preferible. Revisar el ticker si Yahoo vuelve a cambiarlo:
   `python -m scripts.diagnose_market_data` lo muestra como "SIN DATOS".
3. **`^TNX`.** La variacion es % del yield, no puntos base. Para tasas
   conviene mostrar el cambio en pb.
4. **Rate limit.** yfinance 1.7 no lanza excepcion por ticker fallido en un
   batch (solo lo registra en su log), asi que el cliente no distingue "sin
   datos" de "bloqueado". Si reaparecen bloqueos, revisar los logs de
   `yfinance` y considerar cachear la ultima serie buena en SQLite.
5. **Rol de la IA en "En foco".** Hoy la seleccion es deterministica. Pasos
   posibles, en orden de riesgo: (a) que Nix escriba una linea de lectura
   por grafico ("el cobre cae por la huelga en Centinela"), sin elegir
   activos; (b) exponer los candidatos como `chart_ids` del writer
   (`asset_trend:COPPER`) para que la IA ordene entre ellos, siempre
   filtrado por los candidatos deterministicos. La IA nunca deberia poder
   pedir un activo que ninguna noticia menciona.
6. **Cobertura de "En foco".** Con las noticias del 2026-09-28, 8 de 78
   notas mencionan un activo; con solo 3 titulares en el correo, algunos
   dias la seccion no aparecera. Falso positivo conocido: "every dollar I
   earn" (finanzas personales) activa DXY; lo mitiga el filtro de calidad de
   titulares.
7. **Graficos IA (PNG).** `services/ai/chart_renderer.py` podria sumar un
   grafico de linea con `MarketSnapshot.history`, pero siguen apagados en el
   correo por decision del MVP. Si se reactivan: `kaleido==0.2.1` con
   `plotly==5.24.1` funcionan; con plotly >= 6 / kaleido >= 1 cambia la API
   (`engine` eliminado) y se necesita Chrome en la imagen Docker.
8. **Telefonos de <= 375 px.** La tabla de activos no cabe (pasaba tambien
   antes de las sparklines). Se podria reducir el padding lateral de las
   secciones o apilar precio y variacion en una sola columna.

---

## Scraping y noticias: siguientes optimizaciones

1. **Ampliar fuentes chilenas (decision del club).** Diario Financiero publica
   un RSS (`https://www.df.cl/noticias/site/list/port/rss.xml`, 50 notas con
   fecha, probado). Agregarlo es un metodo corto en `ChileNewsClient`
   reutilizando `parse_feed`. Hoy Chile depende de una sola fuente.
2. **GET condicional.** Guardar `ETag`/`Last-Modified` por feed y enviar
   `If-None-Match`/`If-Modified-Since` en el monitor de alto impacto (corre
   cada 15 min) para no bajar feeds sin cambios.
3. **Monitor mas liviano.** `run_high_impact_monitor_once` llama a
   `collect_market_and_news`, que pide los 18 tickers y el BCCh en cada
   corrida (96 veces al dia, tambien de noche y fines de semana). Podria
   reutilizar el ultimo snapshot o limitarse al horario de mercado.
4. **Falsos positivos del clasificador.** `services/news_classifier.py` busca
   palabras clave por substring: `"us "` calza con "focus"/"status", `"sec"`
   con "sector", `"oil"` con "turmoil", `"rate"` con "corporate", e `"ipc"`
   manda el IPC de Mexico a la region Chile. Usar limites de palabra
   (`\b...\b`) y agregar tests de regresion.
5. **Deduplicacion.** Sigue siendo O(n^2) con `SequenceMatcher`; el cache
   `lru_cache(maxsize=512)` es chico para ~100 notas (~5.000 pares). Con el
   filtro de recencia antes de deduplicar el volumen bajo, pero puede
   mejorarse con un indice por tokens.
6. **BCCh.** `BCentralClient` crea un `httpx.Client` que nunca se cierra y
   pide TPM e IPC en serie; sus logs de error no incluyen el mensaje real.

---

## Paquetes: estado tras la limpieza

| Paquete | Uso real | Accion |
|---------|----------|--------|
| `cachetools` | Nunca importado | Eliminado en 0.14.0 |
| `pytest`, `ruff` | Solo desarrollo | Mover a un extra `dev` para aligerar la imagen Docker |
| `plotly`, `kaleido` | Solo render PNG IA (dormido en el correo MVP) | Mantener mientras exista el render IA; las sparklines no los usan |
| `pandas` | Import directo solo en tests | Mantener: dependencia de yfinance |
| `python-dotenv` | No importado | Mantener: `pydantic-settings` lo usa para leer `.env` |
| `lxml` | Parser de BeautifulSoup | Mantener (respaldo HTML de La Tercera) |
| `curl_cffi` | Sesion de yfinance | Quitado de requirements: lo instala yfinance >= 1.0 |

Otros restos: los settings `app_env` y `ai_chart_output_dir` no se leen en
ningun lado. Los pins `lxml==5.3.0` y `pydantic==2.9.2` no compilan en
Python 3.14 (Docker usa 3.11, asi que produccion no se ve afectada, pero si
un entorno local nuevo).

## CI/CD (pendiente de la version anterior)

- GitHub Actions con `pytest` y `ruff check` en cada push.
- `ruff check .` pasa limpio.
