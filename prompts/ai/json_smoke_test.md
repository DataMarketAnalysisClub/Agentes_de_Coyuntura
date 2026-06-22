# Smoke Test: Seleccion de noticias de alto impacto

Analiza las siguientes noticias ya recolectadas y market snapshots, y devuelve un JSON que respete este schema:

```json
{
  "status": "ok",
  "summary": "Resumen ejecutivo breve en espanol",
  "high_impact_titles": ["Titulo 1", "Titulo 2"],
  "cautions": ["Nota de cautela 1"]
}
```

## Reglas

- `status` debe ser siempre "ok".
- `summary`: maximo 3 frases, enfocado en lo mas relevante del dia.
- `high_impact_titles`: titulares (texto exacto del input) que consideres de alto impacto. Solo titulares presentes en el input.
- `cautions`: notas de cautela editorial, riesgos o limitaciones de la informacion.
- No inventes titulares. Si no hay noticias de alto impacto, devuelve lista vacia.
- No inventes cautions genericas si no aplican.

## Noticias (JSON)

{{NEWS_JSON}}

## Market Snapshots (JSON)

{{SNAPSHOTS_JSON}}

## Respuesta esperada

Devuelve SOLO el JSON solicitado, sin texto adicional.
