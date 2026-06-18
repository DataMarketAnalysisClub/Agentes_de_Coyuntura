# Reglas Para Agentes De Codigo

Este repositorio implementa `dmac-market-brief-agent` para el Data Market Analysis Club UDD.

## Principios

- Mantener arquitectura modular: `app/`, `data_sources/`, `services/`, `jobs/`, `storage/` y `tests/`.
- Priorizar MVP estable sobre complejidad tecnica innecesaria.
- No hardcodear credenciales, tokens, usuarios SMTP ni contrasenas.
- Leer configuracion desde variables de entorno y `.env` local.
- Leer credenciales BCCh desde `BCENTRAL_CREDENTIALS_FILE` cuando se use archivo externo; no imprimir su contenido.
- Mantener compatibilidad con Docker y Docker Compose.
- Si una fuente externa falla, registrar `warning` y continuar con las demas.
- Registrar fuentes de datos y conservar historial auditable.
- Agregar tests para cambios relevantes.
- No automatizar WhatsApp con librerias no oficiales. Solo generar texto copiable.
- No hacer scraping agresivo ni intentar evadir paywalls.

## Finanzas Y Comunicacion

- Separar hechos observados de interpretacion financiera.
- No presentar datos estimados o de fuente secundaria como definitivos.
- Incluir notas de cautela cuando corresponda.
- No redactar contenido como recomendacion de inversion.
- Priorizar claridad, prudencia y trazabilidad editorial.

## Datos Y Seguridad

- No commitear `.env`, bases SQLite, logs ni outputs generados.
- No imprimir credenciales en logs.
- Sanitizar errores antes de exponerlos en mensajes de usuario.
- Preferir fuentes oficiales y RSS publicos.
- Documentar cualquier nueva fuente o activo en `README.md`.

## Desarrollo

- Usar Python 3.11 o superior.
- Mantener funciones pequenas y testeables.
- Evitar frameworks web en el MVP salvo requerimiento explicito.
- Usar `pytest` para pruebas.
- Usar `ruff` para estilo cuando se agregue CI.
- Antes de commitear, revisar `git status`, `git diff` y tests relevantes.
