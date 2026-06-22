"""Email brand assets: load and embed the DMAC logo as inline data URI.

The logo is embedded directly into the HTML as a base64 data URI so the
email does not depend on external hosting (which many email clients block).
The encoded URI is cached in memory after the first read.
"""

from __future__ import annotations

import base64
import logging
from functools import lru_cache
from html import escape
from pathlib import Path

logger = logging.getLogger(__name__)


_DEFAULT_LOGO_FILENAME = "Dmac_logo.png"


def _resolve_logo_path(path_str: str | None) -> Path | None:
    if not path_str:
        return None
    path = Path(path_str)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path if path.exists() else None


@lru_cache(maxsize=4)
def _load_logo_bytes(path_str: str) -> bytes | None:
    path = _resolve_logo_path(path_str)
    if path is None:
        return None
    try:
        return path.read_bytes()
    except OSError as exc:
        logger.warning("Failed to read logo file: %s", exc)
        return None


@lru_cache(maxsize=4)
def get_logo_data_uri(path_str: str = "") -> str:
    """Return an inline `data:image/png;base64,...` URI for the logo, or ''."""
    target = path_str or _DEFAULT_LOGO_FILENAME
    data = _load_logo_bytes(target)
    if data is None:
        return ""
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def get_logo_img_tag(
    path_str: str = "",
    width: int = 48,
    alt: str = "DMAC Logo",
) -> str:
    """Return an `<img>` tag with the inline logo, or '' if the logo is missing."""
    uri = get_logo_data_uri(path_str)
    if not uri:
        return ""
    return (
        f'<img src="{uri}" width="{width}" alt="{escape(alt)}" '
        f'style="display: block; border: 0; outline: none; text-decoration: none; '
        f'width: {width}px; height: auto; margin: 0 0 12px 0;">'
    )
