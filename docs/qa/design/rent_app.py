"""QA-only entry for the rent result screens (r4-r6 in measure.js): the published DB has no
rental rows yet, so this runs the real app with ``queries.load_rent_listings`` patched to the
36-row fixture that ``tests/test_rent_guide.py`` uses. Never deployed.

    streamlit run docs/qa/design/rent_app.py --server.port 8502
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scout.ui import queries  # noqa: E402
from tests.test_rent_guide import RENTALS  # noqa: E402

queries.load_rent_listings = lambda: RENTALS
runpy.run_path(str(ROOT / "src" / "scout" / "ui" / "app.py"), run_name="__main__")
