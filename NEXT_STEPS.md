# Siguientes Pasos

## Implementados (v0.2.0)

| Fuente | Tipo | Estado |
|--------|------|--------|
| BCCh API | Datos | ✅ Funcional |
| yfinance | Datos | ✅ Funcional |
| Federal Reserve | RSS | ✅ 20 items |
| ECB | RSS | ✅ 15 items |
| Financial Times | RSS | ✅ 10 items |
| MarketWatch | RSS | ✅ 10 items |
| Investing.com | RSS | ✅ 10 items |
| Ministerio Hacienda | Scraping | ✅ 10 items |
| La Tercera Pulso | Scraping | ✅ 10 items |

---

## Opciones para Continuar

### Opcion A: Robustez de Fuentes
**Objetivo**: Mejorar confiabilidad del sistema

1. **Retry logic + circuit breaker** para todas las fuentes HTTP
   - httpx-retry para reintentos automaticos
   - Implementar circuit breaker con pybreaker

2. **Timeout configurable** para scraping
   - Agregar `SCRAPE_TIMEOUT_SECONDS` a Settings
   - Validar que feeds responden en tiempo razonable

3. **Cache local** para reducir llamadas
   - Implementar cache en memoria para RSS
   - Reducir frecuencia de scraping a sitios chilenos

### Opcion B: Expandir Fuentes
**Objetivo**: Mayor cobertura de informacion

1. **mindicador.cl**
   - API simple para indicadores secundarios (UF, UTM, cobre, IMacec)
   - Sin auth, sin rate limits
   - Complemento a BCCh API

2. **yfinance news**
   - Noticias para commodities (HG=F cobre, GC=F oro, CL=F petroleo)
   - No requiere API key
   - Solo ingles

3. **Nuevas fuentes RSS**
   - Reuters (si funciona)
   - Bloomberg Markets

### Opcion C: Calidad de Datos
**Objetivo**: Mejorar procesamiento de noticias

1. **Mejor deduplicacion semantica**
   - Implementar similarity scoring mas avanzado
   - Usar embeddings para comparar titulos

2. **Clasificacion mejorada**
   - Agregar mas categorias (sectorial, pais)
   - Entrenar modelo simple de clasificacion

3. **Normalizacion de timestamps**
   - Handle timezone correctly
   - Deduplicar por fecha+hora

### Opcion D: CI/CD
**Objetivo**: Automatizar calidad de codigo

1. **GitHub Actions**
   - `pytest` en cada push
   - `ruff check` en cada push
   - Notificacion de fallos

2. **Pre-commit hooks**
   - ruff format antes de commit
   - Tests rapidos antes de push

---

## Recomendacion

**Orden sugerido**: C -> A -> B -> D

1. **Calidad de Datos (C)** - Ya tenemos las fuentes, mejoremos como las procesamos
2. **Robustez (A)** - El servidor 24/7 necesita manejo de fallos elegante
3. **Expandir Fuentes (B)** - Solo si hay gap de informacion especifico
4. **CI/CD (D)** - Automatizar lo que ya funciona bien

---

## Dependencias a agregar para siguientes pasos

```txt
# Para retry + circuit breaker
pybreaker>=1.0.0

# Para cache
cachetools>=5.3.0

# Para yfinance news
# (ya esta incluido en yfinance)

# Para embeddings (opcional)
numpy>=1.26.0
scikit-learn>=1.3.0
```
