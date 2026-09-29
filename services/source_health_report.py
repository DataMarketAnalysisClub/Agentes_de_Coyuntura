"""Persistencia y transiciones de la salud de fuentes (ver services/source_health.py)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.config import Settings, get_settings
from services.source_health import HealthStatus, SourceCheck, SourceKind, next_state
from storage.repositories import SourceHealthRepository, SourceState

logger = logging.getLogger(__name__)

# El monitor de alto impacto corre cada 15 min: ~3.000 registros diarios.
HEALTH_RETENTION_DAYS = 30


@dataclass(frozen=True)
class Transition:
    source: str
    kind: SourceKind
    previous: HealthStatus
    current: HealthStatus
    detail: str = ""


def record_health(
    checks: list[SourceCheck],
    now: datetime,
    repository: SourceHealthRepository | None = None,
) -> list[Transition]:
    """Guarda la corrida, actualiza el estado por fuente y devuelve los cambios de estado."""
    repo = repository or SourceHealthRepository()
    previous_states = repo.states()
    new_states: list[SourceState] = []
    transitions: list[Transition] = []

    for check in checks:
        prev = previous_states.get(check.source)
        prev_state = HealthStatus(prev.state) if prev else None
        prev_status = HealthStatus(prev.last_status) if prev else None
        state = next_state(prev_state, prev_status, check.status)
        baseline = prev_state or HealthStatus.OK
        changed = state is not baseline
        new_states.append(
            SourceState(
                source=check.source,
                kind=str(check.kind),
                state=str(state),
                last_status=str(check.status),
                since=now if prev is None or changed else prev.since,
                last_ok_at=now if check.status is HealthStatus.OK else (prev.last_ok_at if prev else None),
                detail=check.detail,
            )
        )
        if changed:
            transitions.append(Transition(check.source, check.kind, baseline, state, check.detail))

    repo.save_run(now, checks, new_states)
    repo.prune(now - timedelta(days=HEALTH_RETENTION_DAYS))

    not_ok = [check.source for check in checks if check.status is not HealthStatus.OK]
    logger.info("Source health recorded", extra={"checked": len(checks), "not_ok": not_ok})
    for transition in transitions:
        logger.warning(
            "Source health changed",
            extra={
                "source": transition.source,
                "previous": str(transition.previous),
                "current": str(transition.current),
                "detail": transition.detail,
            },
        )
    return transitions


def format_health_table(states: dict[str, SourceState]) -> str:
    """Tabla de texto con el estado vigente, para `python -m app.main health`."""
    if not states:
        return "Sin registros de salud todavia (corre un brief o el monitor)."
    # "Estado" es el reportado (con histeresis); "Corrida" es el resultado
    # de la ultima corrida, que puede adelantarse al estado.
    lines = [f"{'Fuente':22s} {'Tipo':9s} {'Estado':10s} {'Corrida':10s} {'Desde':17s} {'Ultimo ok':17s} Detalle"]
    for state in states.values():
        last_ok = f"{state.last_ok_at:%Y-%m-%d %H:%M}" if state.last_ok_at else "-"
        lines.append(
            f"{state.source[:22]:22s} {state.kind:9s} {state.state:10s} {state.last_status:10s} "
            f"{state.since:%Y-%m-%d %H:%M} {last_ok:17s} {state.detail}"
        )
    return "\n".join(lines)


def notify_transitions(
    transitions: list[Transition],
    checks: list[SourceCheck],
    settings: Settings | None = None,
    sender=None,
) -> bool:
    """Un solo correo a OPS_EMAIL_TO por corrida con cambios de estado."""
    current = settings or get_settings()
    recipients = current.ops_email_to_list
    if not transitions or not recipients:
        return False

    from services.email_formatter import text_to_html
    from services.email_sender import EmailSender

    subject, text_body = build_ops_alert(transitions, checks)
    return (sender or EmailSender(current)).send(
        subject,
        text_body,
        text_to_html(text_body),
        current.email_enabled,
        recipients=recipients,
    )


def build_ops_alert(transitions: list[Transition], checks: list[SourceCheck]) -> tuple[str, str]:
    broken = [t for t in transitions if t.current is not HealthStatus.OK]
    recovered = [t for t in transitions if t.current is HealthStatus.OK]
    parts = []
    if broken:
        parts.append(f"{len(broken)} con problemas")
    if recovered:
        parts.append(f"{len(recovered)} recuperada(s)")
    subject = f"DMAC | Salud de fuentes: {', '.join(parts)}"

    sections: list[tuple[str, list[str]]] = []
    if broken:
        sections.append(
            ("Fuentes con problemas", [f"{t.source} ({t.kind}): {t.current}. {t.detail}".rstrip(". ") for t in broken])
        )
    if recovered:
        sections.append(("Fuentes recuperadas", [f"{t.source} ({t.kind})" for t in recovered]))
    not_ok = [c for c in checks if c.status is not HealthStatus.OK]
    run_lines = [f"{c.source}: {c.status}. {c.detail}".rstrip(". ") for c in not_ok] or ["Todas las fuentes ok."]
    run_lines.append(f"Revisadas: {len(checks)}. Detalle: python -m app.main health")
    sections.append(("Estado de esta corrida", run_lines))
    body = "\n\n".join(
        f"{number}. {title}\n" + "\n".join(f"* {line}" for line in lines)
        for number, (title, lines) in enumerate(sections, start=1)
    )
    return subject, body
