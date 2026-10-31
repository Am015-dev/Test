"""Run app.py under cProfile, one .prof per rerun (C13 profiling). Usage:
    streamlit run docs/qa/speed/profile_app.py --server.headless true --server.port 8502
then drive the app (measure_speed.js with ``only``) and read /tmp/scout-prof/<n>-<page>.prof
with ``python docs/qa/speed/top.py <file>``."""

from __future__ import annotations

import cProfile
import itertools
import runpy
import time
from pathlib import Path

import streamlit as st

OUT = Path("/tmp/scout-prof")
OUT.mkdir(exist_ok=True)
APP = Path(__file__).resolve().parents[3] / "src" / "scout" / "ui" / "app.py"
_n = itertools.count(len(list(OUT.glob("*.prof"))))

prof = cProfile.Profile()
t = time.perf_counter()
prof.enable()
try:
    runpy.run_path(str(APP), run_name="__main__")
finally:
    prof.disable()
    page = str(st.session_state.get("page", "?")).replace("/", "_").replace(" ", "_")
    ms = round((time.perf_counter() - t) * 1000)
    prof.dump_stats(OUT / f"{next(_n):03d}-{page}-{ms}ms.prof")
