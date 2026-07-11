"""Daily digest alerts for the investor.

Config-gated and OFF by default: if neither Telegram nor SMTP is configured in the
environment, ``send_digest`` is a no-op. This keeps the daily run side-effect-free
until the user opts in by filling the relevant ``.env`` values.

The digest leads with the current best opportunities (so it's useful even on a quiet
day), then what changed in the last 24h: new listings and genuine price cuts.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

import requests

from . import finance
from .config import Settings, get_settings
from .ui import format as fmt
from .ui.queries import load_listings, load_recent_price_drops

logger = logging.getLogger(__name__)

DIGEST_SUBJECT = "🏠 Holargos Property Scout — daily digest"


def _net_yield_for(d: dict) -> float | None:
    """Net yield (after Greek buying + operating costs) using the default assumptions.

    None when there is no rent figure to base it on — mirrors the UI detail page so the
    digest and the dashboard agree.
    """
    monthly = d.get("listed_rent") or d.get("est_monthly_rent")
    if not monthly:
        return None
    return finance.net_yield(
        d["price"], monthly * 12, d.get("area_m2"), bool(d.get("is_private_seller"))
    )


def _line(d: dict) -> str:
    area = d.get("search_area") or d.get("neighborhood") or "—"
    gap = d.get("value_gap_pct")
    # Lead with the headline signal: how far below the model's fair value it's priced.
    gap_str = f" · {gap * 100:+.0f}% vs fair" if gap is not None else ""
    gy = d.get("gross_yield")
    gy_str = f" · {gy * 100:.1f}% gross" if gy else ""
    ny = _net_yield_for(d)
    ny_str = f" · {ny * 100:.1f}% net" if ny is not None else ""
    return (
        f"  • [{d['score']:.0f}] {fmt.euro(d['price'])} · "
        f"{fmt.euro_per_m2(d['price_per_m2'])} · {area}{gap_str}{gy_str}{ny_str} · {d['url']}"
    )


def _is_hot(d: dict, min_score: float, min_net_yield: float) -> bool:
    """A new listing worth acting on today: an opportunity, a high score, or a strong
    net yield after costs."""
    if d.get("is_opportunity"):
        return True
    if d.get("score", 0) >= min_score:
        return True
    ny = _net_yield_for(d)
    return ny is not None and ny >= min_net_yield


def build_digest(settings: Settings | None = None) -> str:
    """Plain-text digest: hot deals + top opportunities + last-24h new listings and cuts."""
    settings = settings or get_settings()
    listings = [d for d in load_listings() if not d["excluded"]]
    listings.sort(key=lambda d: d["score"], reverse=True)
    new = [d for d in listings if d["is_new"]]
    opportunities = [d for d in listings if d["is_opportunity"]]
    drops = load_recent_price_drops(hours=24)
    hot = [
        d
        for d in new
        if _is_hot(d, settings.digest_hot_min_score, settings.digest_hot_min_net_yield)
    ]
    watched_drops = [d for d in drops if d.get("is_watched")]

    by_area: dict[str, int] = {}
    for d in listings:
        key = d.get("search_area") or "—"
        by_area[key] = by_area.get(key, 0) + 1
    coverage = ", ".join(f"{a}: {n}" for a, n in sorted(by_area.items()))

    lines = [
        DIGEST_SUBJECT,
        "",
        f"{len(listings)} eligible · {len(new)} new today · {len(drops)} price cuts (24h)",
        f"Coverage — {coverage}",
    ]

    # Lead with hot deals — the whole point of an unsupervised daily run is to surface
    # act-now listings without the owner opening the dashboard.
    if hot:
        lines += ["", f"🔥 HOT DEALS TODAY ({len(hot)}):"]
        lines += [_line(d) for d in hot[:10]]

    lines += ["", f"⭐ TOP OPPORTUNITIES ({len(opportunities)}):"]
    top = opportunities or listings  # fall back to best-scored if none flagged
    lines += [_line(d) for d in top[:10]] or ["  (none)"]

    lines += ["", f"🆕 NEW TODAY ({len(new)}):"]
    lines += ([_line(d) for d in new[:15]]) or ["  (none)"]

    if watched_drops:
        lines += ["", f"⭐ WATCHLIST PRICE CUTS ({len(watched_drops)}):"]
        for d in watched_drops[:15]:
            lines.append(
                f"  • -{d['drop_pct'] * 100:.0f}% {fmt.euro(d['old_price'])} → "
                f"{fmt.euro(d['new_price'])} · {d['title'] or d['source_id']} · {d['url']}"
            )

    lines += ["", f"📉 PRICE CUTS, last 24h ({len(drops)}):"]
    if drops:
        for d in drops[:15]:
            lines.append(
                f"  • -{d['drop_pct'] * 100:.0f}% {fmt.euro(d['old_price'])} → "
                f"{fmt.euro(d['new_price'])} · {d['title'] or d['source_id']} · {d['url']}"
            )
    else:
        lines.append("  (none)")

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


def _send_email(text: str, settings: Settings, subject: str = DIGEST_SUBJECT) -> bool:
    if not (settings.smtp_host and settings.alert_email_to):
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
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


def send_alert(text: str, subject: str = DIGEST_SUBJECT, settings: Settings | None = None) -> bool:
    """Dispatch an arbitrary message to every configured sink. Returns True if sent."""
    settings = settings or get_settings()
    sent = False
    sent |= _send_telegram(text, settings)
    sent |= _send_email(text, settings, subject=subject)
    if not sent:
        logger.info("alerts: no sink configured; message not sent (this is fine).")
    return sent


def send_digest(settings: Settings | None = None) -> bool:
    """Send the digest via any configured sink. Returns True if anything was sent."""
    settings = settings or get_settings()
    return send_alert(build_digest(settings), subject=DIGEST_SUBJECT, settings=settings)
