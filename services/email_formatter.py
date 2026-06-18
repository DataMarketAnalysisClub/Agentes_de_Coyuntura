from html import escape


def text_to_html(text_body: str) -> str:
    """Convert plain text brief content into simple email-safe HTML."""

    paragraphs = []
    for block in text_body.split("\n\n"):
        safe = escape(block).replace("\n", "<br>")
        paragraphs.append(f"<p>{safe}</p>")
    return "\n".join(paragraphs)


def build_email_html(subject: str, text_body: str) -> str:
    content = text_to_html(text_body)
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>{escape(subject)}</title>
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.5; color: #111827;">
  <h1 style="font-size: 20px;">{escape(subject)}</h1>
  {content}
</body>
</html>"""
