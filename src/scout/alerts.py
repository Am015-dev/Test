"""Digest alerts for NEW + PRICE↓ listings (Phase 7).

Config-gated and OFF by default: if neither Telegram nor SMTP is configured in the
environment, ``send_digest`` is a no-op. This keeps the daily run side-effect-free
until the user opts in by filling the relevant ``.env`` values.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

import requests

from .config import Settings, get_settings
from .ui import format as fmt
from .ui.queries import load_listings

logger = logging.getLogger(__name__)


def build_digest() -> str:
    """Plain-text digest of new + price-dropped, hard-filter-passing listings."""
    listings = [d for d in load_listings() if not d["excluded"]]
    new = sorted((d for d in listings if d["is_new"]), key=lambda d: d["score"], reverse=True)
    dropped = [d for d in listings if d["price_dropped"]]

    lines = ["🏠 Holargos Property Scout — daily digest", ""]
    lines.append(f"NEW today ({len(new)}):")
    for d in new[:15]:
        lines.append(
            f"  • [{d['score']:.0f}] {fmt.euro(d['price'])} · {fmt.euro_per_m2(d['price_per_m2'])}"
            f" · {d['neighborhood'] or '—'} · {d['url']}"
        )
    lines.append("")
    lines.append(f"PRICE DROPS ({len(dropped)}):")
    for d in dropped[:15]:
        lines.append(
            f"  • {fmt.euro(d['first_price'])} → {fmt.euro(d['price'])}"
            f" · {d['title'] or d['source_id']} · {d['url']}"
        )
    return "\n".join(lines)


def _send_telegram(text: str, settings: Settings) -> bool:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return False
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        resp = requests.post(
            url, json={"chat_id": settings.telegram_chat_id, "text": text}, timeout=10
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.warning("telegram send failed: %s", exc)
        return False


def _send_email(text: str, settings: Settings) -> bool:
    if not (settings.smtp_host and settings.alert_email_to):
        return False
    msg = EmailMessage()
    msg["Subject"] = "Holargos Property Scout — daily digest"
    msg["From"] = settings.smtp_user or "scout@localhost"
    msg["To"] = settings.alert_email_to
    msg.set_content(text)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        logger.warning("email send failed: %s", exc)
        return False


def send_digest(settings: Settings | None = None) -> bool:
    """Send the digest via any configured sink. Returns True if anything was sent."""
    settings = settings or get_settings()
    text = build_digest()
    sent = False
    sent |= _send_telegram(text, settings)
    sent |= _send_email(text, settings)
    if not sent:
        logger.info("alerts: no sink configured; digest not sent (this is fine).")
    return sent
