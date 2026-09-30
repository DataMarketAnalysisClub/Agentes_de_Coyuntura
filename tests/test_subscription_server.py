import threading
import urllib.error
import urllib.request
from urllib.parse import urlencode

import pytest

from app.config import Settings
from app.subscription_server import make_server
from services.subscriptions import SubscriptionService
from storage.subscribers import SubscriberStatus


class FakeSender:
    def __init__(self) -> None:
        self.sent = []

    def send(self, subject, text_body, html_body, enabled, recipients=None):
        self.sent.append(text_body)
        return True


@pytest.fixture
def server(subscriber_repository):
    settings = Settings(
        mailing_public_url="https://dmac.example.ts.net",
        mailing_web_host="127.0.0.1",
        mailing_web_port=0,
        email_enabled=True,
        ops_email_to="dmac@udd.cl",
    )
    sender = FakeSender()
    service = SubscriptionService(subscriber_repository, settings, sender=sender)
    httpd = make_server(service, settings)
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base, subscriber_repository, sender
    httpd.shutdown()
    httpd.server_close()


def _request(url, data=None, headers=None):
    body = urlencode(data).encode() if isinstance(data, dict) else data
    request = urllib.request.Request(url, data=body, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read().decode(), response.headers
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode(), error.headers


def _subscribe_and_get_token(base, repository, email="ana@udd.cl"):
    status, _, _ = _request(f"{base}/suscribir", {"email": email, "consent": "1"})
    assert status == 200
    return repository.get_by_email(email).token


def test_form_page_has_privacy_note_and_security_headers(server) -> None:
    base, _, _ = server
    status, body, headers = _request(f"{base}/")

    assert status == 200
    assert 'action="/suscribir"' in body
    assert "dmac@udd.cl" in body
    assert "no constituye recomendación de inversión" in body
    assert headers["Referrer-Policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert headers["Cache-Control"] == "no-store"


def test_subscribe_requires_consent_and_valid_email(server) -> None:
    base, repository, sender = server

    status, body, _ = _request(f"{base}/suscribir", {"email": "ana@udd.cl"})
    assert status == 400 and "Debes aceptar" in body

    status, body, _ = _request(f"{base}/suscribir", {"email": "nada", "consent": "1"})
    assert status == 400 and "correo válido" in body
    assert repository.find() == [] and sender.sent == []


def test_honeypot_pretends_success_without_subscribing(server) -> None:
    base, repository, sender = server
    status, body, _ = _request(f"{base}/suscribir", {"email": "bot@spam.cl", "consent": "1", "website": "x"})

    assert status == 200 and "Revisa tu correo" in body
    assert repository.find() == [] and sender.sent == []


def test_get_confirm_does_not_confirm_but_post_does(server) -> None:
    base, repository, _ = server
    token = _subscribe_and_get_token(base, repository)

    status, body, _ = _request(f"{base}/confirmar?t={token}")
    assert status == 200 and "Confirmar suscripción" in body
    assert repository.get_by_email("ana@udd.cl").status is SubscriberStatus.PENDING

    status, body, _ = _request(f"{base}/confirmar", {"t": token})
    assert status == 200 and "confirmada" in body
    assert repository.get_by_email("ana@udd.cl").status is SubscriberStatus.ACTIVE


def test_get_unsubscribe_shows_button_and_one_click_post_unsubscribes(server) -> None:
    base, repository, _ = server
    token = _subscribe_and_get_token(base, repository)
    _request(f"{base}/confirmar", {"t": token})

    status, body, _ = _request(f"{base}/baja?t={token}")
    assert status == 200 and "Cancelar suscripción" in body
    assert repository.get_by_email("ana@udd.cl").status is SubscriberStatus.ACTIVE

    # POST de un clic de Gmail/Outlook (RFC 8058): token en la URL.
    status, _, _ = _request(f"{base}/baja?t={token}", b"List-Unsubscribe=One-Click",
                            {"Content-Type": "application/x-www-form-urlencoded"})
    assert status == 200
    assert repository.get_by_email("ana@udd.cl").status is SubscriberStatus.UNSUBSCRIBED

    status, body, _ = _request(f"{base}/baja?t={token}", {"t": token})
    assert status == 200 and "ya estaba cancelada" in body


def test_one_click_post_as_multipart(server) -> None:
    base, repository, _ = server
    token = _subscribe_and_get_token(base, repository)
    boundary = "xYz"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"List-Unsubscribe\"\r\n\r\n"
            f"One-Click\r\n--{boundary}--\r\n").encode()

    status, _, _ = _request(f"{base}/baja?t={token}", body,
                            {"Content-Type": f"multipart/form-data; boundary={boundary}"})
    assert status == 200
    assert repository.get_by_email("ana@udd.cl").status is SubscriberStatus.UNSUBSCRIBED


def test_invalid_tokens_and_unknown_paths(server) -> None:
    base, _, _ = server

    assert _request(f"{base}/baja?t=corto")[0] == 400
    assert _request(f"{base}/confirmar?t=<script>")[0] == 400
    assert _request(f"{base}/baja", {"t": "z" * 43})[0] == 400
    assert _request(f"{base}/no-existe")[0] == 404


def test_oversized_body_is_rejected(server) -> None:
    base, repository, _ = server
    status, _, _ = _request(f"{base}/suscribir", {"email": "a@udd.cl", "consent": "1", "pad": "x" * 5000})

    assert status == 413
    assert repository.find() == []


def test_health_reports_database(server) -> None:
    base, _, _ = server
    assert _request(f"{base}/salud")[:2] == (200, "ok")


def test_database_failure_returns_503_without_details(server, monkeypatch) -> None:
    base, repository, _ = server

    def boom(*args, **kwargs):
        raise RuntimeError("password=secreto")

    monkeypatch.setattr(repository, "get_by_email", boom)
    status, body, _ = _request(f"{base}/suscribir", {"email": "ana@udd.cl", "consent": "1"})

    assert status == 503
    assert "secreto" not in body
