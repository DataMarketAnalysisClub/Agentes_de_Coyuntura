"""Servicio web de suscripcion (formulario, confirmacion y baja).

Pequeno y aislado a proposito (`AGENTS.md` pide evitar frameworks web en el
MVP): `http.server` de la libreria estandar, sin estado propio, todo en MySQL.
Se publica con HTTPS mediante Tailscale Funnel (ver `DEPLOY.md`).

Rutas:
    GET  /                 formulario de inscripcion
    POST /suscribir        alta -> correo de confirmacion
    GET  /confirmar?t=...  pagina con boton "Confirmar"
    POST /confirmar        confirma (pending -> active)
    GET  /baja?t=...       pagina con boton "Cancelar suscripcion"
    POST /baja?t=...       baja; tambien el POST de un clic de Gmail/Outlook
                           (RFC 8058, cuerpo `List-Unsubscribe=One-Click`)
    GET  /salud            200 si MySQL responde

Confirmar y dar de baja exigen POST: los antivirus de correo (Outlook Safe
Links, etc.) abren los links con GET y no deben poder inscribir ni borrar a
nadie.
"""

from __future__ import annotations

import logging
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from app.config import Settings, get_settings
from services.subscriptions import (
    ConfirmOutcome,
    SubscribeOutcome,
    SubscriptionService,
    UnsubscribeOutcome,
    is_well_formed_token,
)

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 4096

_SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none';"
        " base-uri 'none'"
    ),
    # Los links llevan el token en la URL: nunca mandarlo como Referer.
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
}

PRIVACY_NOTE = (
    "Guardamos solo tu correo y las fechas de alta y baja, para enviarte DMAC Brief"
    " (resumen de coyuntura financiera del Data Market Analysis Club UDD, días hábiles)."
    " No lo compartimos con terceros. Puedes darte de baja cuando quieras desde el enlace"
    " al pie de cada correo, o pedir que borremos tus datos escribiendo a {contact}."
)


def _page(title: str, body: str) -> bytes:
    return (
        "<!doctype html><html lang=\"es\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{escape(title)} · DMAC Brief</title>"
        "<style>"
        ":root{color-scheme:light dark;--ink:#1a1a1a;--paper:#fff;--page:#f4f4f1;--muted:#5c5c58;--rule:#d9d9d4}"
        "@media (prefers-color-scheme:dark){:root{--ink:#ececea;--paper:#1c1c1b;--page:#111110;"
        "--muted:#a3a39e;--rule:#3a3a38}}"
        "body{margin:0;background:var(--page);color:var(--ink);font:16px/1.6 system-ui,sans-serif}"
        "main{max-width:520px;margin:0 auto;padding:32px 16px}"
        ".card{background:var(--paper);border:1px solid var(--rule);padding:28px}"
        "h1{font-family:Georgia,'Times New Roman',serif;font-size:30px;margin:0 0 4px}"
        ".kicker{font-size:12px;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted)}"
        "label{display:block;font-weight:600;margin:18px 0 6px}"
        "input[type=email]{width:100%;box-sizing:border-box;padding:10px 12px;font-size:16px;"
        "border:1px solid var(--rule);background:var(--paper);color:var(--ink)}"
        ".check{display:flex;gap:10px;align-items:flex-start;font-weight:400;font-size:14px}"
        ".check input{margin-top:5px}"
        "button{margin-top:18px;background:var(--ink);color:var(--paper);border:0;padding:12px 22px;"
        "font-size:16px;font-weight:700;cursor:pointer}"
        ".note{font-size:13px;color:var(--muted)}"
        ".hp{position:absolute;left:-10000px}"
        "</style></head><body><main><div class=\"card\">"
        "<div class=\"kicker\">Data Market Analysis Club UDD</div>"
        f"<h1>DMAC Brief</h1>{body}</div></main></body></html>"
    ).encode()


def _message(title: str, text: str) -> bytes:
    return _page(title, f"<p>{escape(text)}</p>")


def subscribe_form(settings: Settings, error: str = "") -> bytes:
    contact = escape(settings.ops_email_to_list[0] if settings.ops_email_to_list else "el club")
    error_html = f"<p role=\"alert\"><strong>{escape(error)}</strong></p>" if error else ""
    return _page(
        "Suscribirse",
        "<p>Resumen de coyuntura financiera: mercados, Chile y el mundo, cada día hábil"
        " en tu correo.</p>"
        f"{error_html}"
        "<form method=\"post\" action=\"/suscribir\">"
        "<label for=\"email\">Correo</label>"
        "<input type=\"email\" id=\"email\" name=\"email\" required maxlength=\"254\" autocomplete=\"email\">"
        # Trampa para bots: los humanos no ven el campo.
        "<div class=\"hp\" aria-hidden=\"true\"><label for=\"website\">No llenar</label>"
        "<input type=\"text\" id=\"website\" name=\"website\" tabindex=\"-1\" autocomplete=\"off\"></div>"
        "<label class=\"check\"><input type=\"checkbox\" name=\"consent\" value=\"1\" required>"
        "<span>Acepto recibir DMAC Brief y el tratamiento de mi correo descrito abajo.</span></label>"
        "<button type=\"submit\">Suscribirme</button></form>"
        f"<p class=\"note\">{PRIVACY_NOTE.format(contact=contact)}</p>"
        "<p class=\"note\">DMAC Brief es material informativo y no constituye recomendación de inversión.</p>",
    )


def _token_form(action: str, token: str, text: str, button: str) -> bytes:
    return _page(
        button,
        f"<p>{escape(text)}</p><form method=\"post\" action=\"/{action}?t={escape(token, quote=True)}\">"
        f"<input type=\"hidden\" name=\"t\" value=\"{escape(token, quote=True)}\">"
        f"<button type=\"submit\">{escape(button)}</button></form>",
    )


SUBSCRIBE_MESSAGES = {
    # Mismo texto si el correo ya estaba activo o hubo freno: no revela quien
    # esta inscrito.
    SubscribeOutcome.CONFIRMATION_SENT: "Revisa tu correo: te enviamos un enlace para confirmar la suscripción.",
    SubscribeOutcome.ALREADY_ACTIVE: "Revisa tu correo: te enviamos un enlace para confirmar la suscripción.",
    SubscribeOutcome.THROTTLED: "Revisa tu correo: te enviamos un enlace para confirmar la suscripción.",
    SubscribeOutcome.SEND_FAILED: "No pudimos enviar el correo de confirmación. Intenta de nuevo más tarde.",
}
CONFIRM_MESSAGES = {
    ConfirmOutcome.CONFIRMED: "¡Listo! Tu suscripción está confirmada. Recibirás el próximo DMAC Brief.",
    ConfirmOutcome.ALREADY_ACTIVE: "Tu suscripción ya estaba confirmada.",
    ConfirmOutcome.EXPIRED: "El enlace venció. Vuelve a inscribirte para recibir uno nuevo.",
    ConfirmOutcome.INVALID: "El enlace no es válido. Vuelve a inscribirte para recibir uno nuevo.",
}
UNSUBSCRIBE_MESSAGES = {
    UnsubscribeOutcome.UNSUBSCRIBED: "Listo: cancelamos tu suscripción. No recibirás más correos de DMAC Brief.",
    UnsubscribeOutcome.ALREADY_UNSUBSCRIBED: "Tu suscripción ya estaba cancelada.",
    UnsubscribeOutcome.INVALID: "El enlace no es válido o ya no existe.",
}


class SubscriptionHandler(BaseHTTPRequestHandler):
    server_version = "dmac-subscriptions"
    sys_version = ""
    # Corta conexiones lentas o colgadas (cada una ocupa un hilo).
    timeout = 15
    # Asignados por `make_server`.
    service: SubscriptionService
    settings: Settings

    def do_GET(self) -> None:  # noqa: N802 (nombre de http.server)
        path, query = self._route()
        token = (query.get("t") or [""])[0]
        if path == "/":
            self._respond(HTTPStatus.OK, subscribe_form(self.settings))
        elif path == "/confirmar":
            if not is_well_formed_token(token):
                self._respond(HTTPStatus.BAD_REQUEST, _message("Enlace inválido", CONFIRM_MESSAGES[ConfirmOutcome.INVALID]))
                return
            self._respond(HTTPStatus.OK, _token_form(
                "confirmar", token, "Confirma que quieres recibir DMAC Brief en tu correo.", "Confirmar suscripción"))
        elif path == "/baja":
            if not is_well_formed_token(token):
                self._respond(HTTPStatus.BAD_REQUEST,
                              _message("Enlace inválido", UNSUBSCRIBE_MESSAGES[UnsubscribeOutcome.INVALID]))
                return
            self._respond(HTTPStatus.OK, _token_form(
                "baja", token, "¿Quieres dejar de recibir DMAC Brief?", "Cancelar suscripción"))
        elif path == "/salud":
            self._health()
        else:
            self._respond(HTTPStatus.NOT_FOUND, _message("No encontrado", "Esta página no existe."))

    def do_POST(self) -> None:  # noqa: N802
        path, query = self._route()
        form = self._read_form()
        if form is None:
            self._respond(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, _message("Error", "Solicitud demasiado grande."))
            return
        token = (form.get("t") or query.get("t") or [""])[0]
        try:
            if path == "/suscribir":
                self._subscribe(form)
            elif path == "/confirmar":
                outcome = self.service.confirm(token)
                status = HTTPStatus.OK if outcome in (ConfirmOutcome.CONFIRMED, ConfirmOutcome.ALREADY_ACTIVE) \
                    else HTTPStatus.BAD_REQUEST
                self._respond(status, _message("Suscripción", CONFIRM_MESSAGES[outcome]))
            elif path == "/baja":
                one_click = (form.get("List-Unsubscribe") or [""])[0] == "One-Click"
                outcome = self.service.unsubscribe(token, detail="one-click" if one_click else "link")
                status = HTTPStatus.BAD_REQUEST if outcome is UnsubscribeOutcome.INVALID else HTTPStatus.OK
                self._respond(status, _message("Suscripción", UNSUBSCRIBE_MESSAGES[outcome]))
            else:
                self._respond(HTTPStatus.NOT_FOUND, _message("No encontrado", "Esta página no existe."))
        except Exception:
            # Sin detalles al usuario ni tokens/correos en el log.
            logger.exception("Subscription request failed", extra={"path": path})
            self._respond(HTTPStatus.SERVICE_UNAVAILABLE,
                          _message("No disponible", "El servicio no está disponible. Intenta más tarde."))

    def _subscribe(self, form: dict[str, list[str]]) -> None:
        if (form.get("website") or [""])[0]:
            # Bot: respuesta de exito sin hacer nada.
            self._respond(HTTPStatus.OK, _message("Suscripción", SUBSCRIBE_MESSAGES[SubscribeOutcome.CONFIRMATION_SENT]))
            return
        if (form.get("consent") or [""])[0] != "1":
            self._respond(HTTPStatus.BAD_REQUEST,
                          subscribe_form(self.settings, "Debes aceptar para suscribirte."))
            return
        outcome = self.service.subscribe((form.get("email") or [""])[0])
        if outcome is SubscribeOutcome.INVALID_EMAIL:
            self._respond(HTTPStatus.BAD_REQUEST, subscribe_form(self.settings, "Ingresa un correo válido."))
            return
        status = HTTPStatus.SERVICE_UNAVAILABLE if outcome is SubscribeOutcome.SEND_FAILED else HTTPStatus.OK
        self._respond(status, _message("Suscripción", SUBSCRIBE_MESSAGES[outcome]))

    def _health(self) -> None:
        try:
            self.service.repository.ping()
        except Exception:
            logger.warning("Subscription health check failed: MySQL unreachable")
            self._respond(HTTPStatus.SERVICE_UNAVAILABLE, b"mysql: error", content_type="text/plain")
            return
        self._respond(HTTPStatus.OK, b"ok", content_type="text/plain")

    def _route(self) -> tuple[str, dict[str, list[str]]]:
        parts = urlsplit(self.path)
        return parts.path.rstrip("/") or "/", parse_qs(parts.query)

    def _read_form(self) -> dict[str, list[str]] | None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length > MAX_BODY_BYTES:
            return None
        raw = self.rfile.read(length) if length > 0 else b""
        content_type = (self.headers.get("Content-Type") or "").lower()
        if content_type.startswith("multipart/form-data"):
            # RFC 8058 permite multipart; solo interesa el campo One-Click.
            text = raw.decode("utf-8", "replace")
            return {"List-Unsubscribe": ["One-Click"]} if "One-Click" in text else {}
        return parse_qs(raw.decode("utf-8", "replace"), max_num_fields=20)

    def _respond(self, status: HTTPStatus, body: bytes, content_type: str = "text/html; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in _SECURITY_HEADERS.items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        # El access log por defecto incluiria la URL con el token.
        logger.info("Subscription request", extra={"method": self.command, "path": urlsplit(self.path).path,
                                                     "status": args[1] if len(args) > 1 else ""})


def make_server(service: SubscriptionService, settings: Settings) -> ThreadingHTTPServer:
    handler = type("BoundSubscriptionHandler", (SubscriptionHandler,), {"service": service, "settings": settings})
    server = ThreadingHTTPServer((settings.mailing_web_host, settings.mailing_web_port), handler)
    server.daemon_threads = True
    return server


def run_subscription_server(settings: Settings | None = None) -> None:
    from storage.subscribers import SubscriberRepository

    current = settings or get_settings()
    if not current.mailing_public_url:
        logger.warning("MAILING_PUBLIC_URL vacio: los links de confirmacion y baja no funcionaran")
    repository = SubscriberRepository.from_settings(current)
    repository.init_schema()
    server = make_server(SubscriptionService(repository, current), current)
    logger.info("Subscription server listening",
                extra={"host": current.mailing_web_host, "port": current.mailing_web_port})
    try:
        server.serve_forever()
    finally:
        server.server_close()
