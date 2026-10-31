"""Retired: «Βρες μου σπίτι» is now the «Οδηγός» (``ui/guide.py``).

Kept only so the navigation entry keeps working until the app shell points at
``guide.page`` directly; it renders the guide, nothing else.
"""

from __future__ import annotations

from scout.ui import guide

TITLE = "Βρες μου σπίτι"
arrange = guide.arrange


def page_find(listings: list[dict]) -> None:
    guide.page(listings)
