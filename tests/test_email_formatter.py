from services.email_formatter import build_email_html, text_to_html


def test_text_to_html_escapes_content() -> None:
    html = text_to_html("Titulo\n<script>alert('x')</script>")

    assert "&lt;script&gt;" in html
    assert "<br>" in html


def test_build_email_html_includes_subject_and_body() -> None:
    html = build_email_html("DMAC Test", "Contenido")

    assert "DMAC Test" in html
    assert "Contenido" in html
    assert "<!doctype html>" in html
