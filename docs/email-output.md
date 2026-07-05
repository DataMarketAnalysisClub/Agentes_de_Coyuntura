# Email output: estructura y comportamiento

Documento de referencia sobre como se ve el email del morning brief y market
close que envia `dmac-market-brief-agent`. Util para validar cambios en el
formatter y para entender que recibe el destinatario.

## Estructura general

El email es un multipart/alternative con dos partes:

1. `text/plain`: version texto plano, generada por `services.summarizer.py`
2. `text/html`: version con branding DMAC, generada por
   `services.email_formatter.build_email_html`

Tamano tipico del HTML: 60-80 KB (sin imagenes IA embebidas en MVP).

## Orden de secciones en el HTML

### Cuando la IA funciona (`AI_BRIEF_ENABLED=true` y Ollama responde)

1. **Header** (gradient azul con logo DMAC, subject, intro "Estimado Equipo...")
2. **Analisis de Nix** (card destacada, al inicio, badge "DMAC AI", gradient header)
   - Resumen ejecutivo (bullets)
   - Seccion por region (Chile / Global / Reino Unido / EE.UU.) con texto + bullets
   - A vigilar (bullets)
   - Cautelas (bullets)
3. **Sentimiento de mercado** (score 0-100, drivers, fuente)
4. **Asset table** (estatica, JS-free): Activo | Precio | Var % | Fuente
5. **Titulares por region** (barras horizontales estaticas)
6. **Titulares principales** (lista ejecutiva con links a la fuente y region)
7. **Footer** (disclaimer, "Nix Assistant, DMAC UDD", copyright)

Las secciones deterministicas de `summarizer.py` (Resumen ejecutivo, Chile,
Latam, EE.UU., Internacional, Que mirar hoy, Lectura DMAC) **NO se renderizan**
porque la IA las reemplaza. Esto se controla con `include_deterministic_brief=False`
en `build_email_html` cuando hay IA.

### Cuando la IA falla o esta deshabilitada

1. **Header**
2. Secciones deterministicas de `summarizer.py`:
   1. Resumen ejecutivo
   2. Chile
   3. Latam
   4. Estados Unidos
   5. Internacional
   6. Que mirar hoy
   7. Lectura DMAC
3. Sentimiento de mercado
4. Asset table
5. Titulares por region
6. Titulares principales
7. Footer

## Comportamiento por cliente de email

| Cliente | Estado |
|---------|--------|
| Outlook web (computador) | OK, todo se ve |
| Outlook mobile (Android/iOS) | OK, todo se ve |
| Gmail web | OK (no probado con IA real, fallback OK) |
| Apple Mail | Deberia funcionar (no probado) |
| Clientes antiguos (Outlook 2016, Lotus Notes) | Las barras estaticas funcionan; el badge DMAC AI puede no verse con gradient |

## Visualizaciones en el email (MVP)

### Estaticas (siempre presentes, JS-free)

- **Asset table**: tabla HTML con `border: 1px solid`, `border-radius: 6px`
- **Sentimiento de mercado**: barra 0-100 con drivers principales desde
  `yfinance` y Google Finance cuando esta disponible
- **Titulares por region bars**: divs con `width: N%` por cantidad de titulares
- Renderizadas por `services/email_charts.py`

Estas funcionan en TODOS los clientes de email sin problemas, incluyendo
Outlook mobile, Outlook web, Gmail, Apple Mail.

### IA-sugeridas (DESHABILITADAS en MVP)

El codigo de render esta disponible en `services/ai/chart_renderer.py`
(funcion `render_charts_as_png`) pero **NO se invoca** en el flujo del email
productivo. El job descarta los charts antes de pasarlos al formatter:

```python
def _build_nix_charts_cid_map(chart_pngs: dict[str, bytes]) -> dict[str, bytes]:
    del chart_pngs  # intentionally discarded in MVP
    return {}
```

Razones del descarte en MVP:

- Outlook mobile / web tienen problemas historicos con imagenes embebidas
  (cid: multipart/related y base64 inline mostraban icono de imagen rota)
- El tamano del email crecia ~3x con base64 (~200KB vs ~60KB)
- El valor agregado vs las barras estaticas no justifica el costo de
  complejidad en MVP

Cuando se reactive: actualizar `_build_nix_charts_cid_map` para devolver
`chart_pngs` y restaurar el bloque que renderiza base64 en
`_nix_analysis_section`.

## Salida de texto plano (text/plain)

La parte text/plain sigue el formato definido por `services.summarizer.py`:

```
DMAC Morning Brief | Coyuntura Financiera | 2026-06-20

1. Resumen ejecutivo
* Titular uno (Fuente)
* Titular dos (Fuente)

2. Chile
USD/CLP: 903.15 (+1.90%)
Cobre: 6.34 (-0.59%)
IPSA: 10,888.43 (s/d)
* Titular Chile (Fuente)

3. Latam
...

7. Lectura DMAC
* Hechos: los datos anteriores provienen de fuentes configuradas y pueden tener rezago.
* Interpretacion: lectura preliminar y prudente; no constituye recomendacion de inversion.
```

## Estilo del HTML

- **Colores de marca** (`services/email_formatter.py`):
  - Primario: `#1d4ed8` (azul)
  - Primario oscuro: `#1e3a8a`
  - Acento: `#0891b2` (cyan)
  - Positivo: `#16a34a` (verde)
  - Negativo: `#dc2626` (rojo)
- **Tipografia**: `Arial, sans-serif` (web-safe, todos los clientes la soportan)
- **Ancho maximo**: 640px
- **Padding**: 24px lateral, 12-20px entre secciones
- **Sin JavaScript** (clientes de email lo strippean)
- **Sin CSS externo** (todo inline)

## Validacion visual

Para previsualizar sin enviar por SMTP:

```bash
DRY_RUN=true python -m app.main morning
# Luego abre outputs/briefs/morning_brief_YYYYMMDD_HHMMSS.html en un browser
```

Tambien puedes comparar el HTML contra la salida de texto plano abriendo
ambos archivos lado a lado.

## Cuando el mercado esta cerrado o no hay datos

- `MarketSnapshot` con `price=None` y `change_pct=None` se omite de la tabla
- Si TODOS los snapshots estan vacios, la tabla muestra "Mercado cerrado o
  sin datos disponibles al momento."
- `render_news_distribution_bars` retorna string vacio si no hay noticias

## Metricas de envio

- Tiempo total del morning brief: ~3-5 min (28s data collection + 2-3 min Ollama + 5s render)
- Tamano HTML: 60-80 KB
- Tamano total email: ~80-100 KB
- Subject: `DMAC Morning Brief | Coyuntura Financiera | YYYY-MM-DD`
- From: configurable via `EMAIL_FROM`
- To: configurable via `EMAIL_TO`
