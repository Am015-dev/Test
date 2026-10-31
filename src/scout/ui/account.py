"""Who is using the app, and where their preferences live.

Two ways to be recognised, one API (``current_user``, ``login_ui``, ``logout``, ``storage``):

* **Google sign-in** — when Streamlit secrets have an ``[auth]`` section, ``st.login()`` /
  ``st.user`` (Streamlit's OIDC). The profile key is ``google:<email>``.
* **Profile** — otherwise «Όνομα» + 4-digit PIN. The PIN is stored only as
  ``sha256(salt + pin)`` with a per-profile random salt, inside the private gist document
  (``profiles[key] = {"name", "salt", "hash", "fails", "locked_until", "data": {...}}``).
  5 wrong PINs lock that name for 10 minutes; the counter lives in the gist, so a new tab
  does not reset it. The PIN guards preferences only — see docs/ACCOUNTS.md.

No profile = the "anonymous" profile (the gist's top-level keys, where everything saved before
accounts existed still lives). Without a storage token everything is session-only.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import re
import secrets
import time
import unicodedata

import streamlit as st

from scout import shortlist

MAX_FAILS = 5
LOCK_S = 10 * 60
PIN_RE = re.compile(r"\d{4}")
SESSION_KEY = "profile"  # the signed-in profile key (PIN profiles)
_CACHE = "_store_cache"
_MISSING = object()
# Per-session copies of stored data, dropped when the user changes.
_SESSION_CACHES = ("watch", "watch_persisted", "pick_review", "review_persisted", _CACHE)


class ProfileError(Exception):
    """A message for the person (Greek, no PIN in it)."""


# ---- pure helpers (no Streamlit) ---------------------------------------------------------


def profile_key(name: str) -> str:
    """Names match ignoring case, accents and extra spaces: «Μαρία », «ΜΑΡΙΑ» and «μαρια» are
    one profile (casefold also folds final ς into σ)."""
    bare = unicodedata.normalize("NFD", " ".join(name.split()).casefold())
    return "".join(c for c in bare if not unicodedata.combining(c))


def hash_pin(salt: str, pin: str) -> str:
    return hashlib.sha256((salt + pin).encode()).hexdigest()


def _profiles(doc: dict) -> dict:
    return doc.setdefault("profiles", {})


def create_profile(name: str, pin: str) -> str:
    """New PIN profile; returns its key. The very first profile starts with a copy of the
    anonymous favourites, verdicts and saved searches, so the owner's earlier choices follow
    them into their profile (the anonymous copy stays where it was)."""
    key = profile_key(name)
    if not key:
        raise ProfileError("Γράψε ένα όνομα.")
    if not PIN_RE.fullmatch(pin or ""):
        raise ProfileError("Το PIN είναι 4 ψηφία.")
    doc = shortlist._read_all()
    profiles = _profiles(doc)
    if key in profiles:
        raise ProfileError("Υπάρχει ήδη προφίλ με αυτό το όνομα — πάτα «Σύνδεση».")
    first = not any(p.get("hash") for p in profiles.values())
    salt = secrets.token_hex(16)
    data = {k: copy.deepcopy(doc.get(k)) for k in shortlist.USER_KEYS if doc.get(k)}
    profiles[key] = {
        "name": " ".join(name.split()),
        "salt": salt,
        "hash": hash_pin(salt, pin),
        "fails": 0,
        "locked_until": 0,
        "data": data if first else {},
    }
    shortlist._write_all(doc)
    return key


def check_pin(name: str, pin: str, now: float | None = None) -> str:
    """The profile key if the PIN is right; otherwise ProfileError. Counts wrong tries in the
    stored document and locks the name for LOCK_S after MAX_FAILS of them."""
    now = time.time() if now is None else now
    key = profile_key(name)
    doc = shortlist._read_all()
    prof = _profiles(doc).get(key)
    if not prof or not prof.get("hash"):
        raise ProfileError("Δεν υπάρχει προφίλ με αυτό το όνομα — πάτα «Νέο προφίλ».")
    if prof.get("locked_until", 0) > now:
        mins = -(-(prof["locked_until"] - now) // 60)
        raise ProfileError(f"Πολλές λάθος προσπάθειες — δοκίμασε ξανά σε {int(mins)} λεπτά.")
    if hmac.compare_digest(hash_pin(prof["salt"], pin or ""), prof["hash"]):
        if prof.get("fails") or prof.get("locked_until"):
            prof["fails"], prof["locked_until"] = 0, 0
            shortlist._write_all(doc)
        return key
    fails = prof.get("fails", 0) + 1
    if fails >= MAX_FAILS:
        prof["fails"], prof["locked_until"] = 0, now + LOCK_S
        shortlist._write_all(doc)
        raise ProfileError("Λάθος PIN. Το προφίλ κλείδωσε για 10 λεπτά.")
    prof["fails"] = fails
    shortlist._write_all(doc)
    left = MAX_FAILS - fails
    raise ProfileError(f"Λάθος PIN. Απομένουν {left} προσπάθει{'α' if left == 1 else 'ες'}.")


# ---- the per-user store --------------------------------------------------------------------


class Store:
    """``get``/``set`` on the signed-in user's part of the stored document (anonymous profile
    when nobody is signed in). Fail-soft: without a token, or if the store can't be reached,
    values live in this session only and ``persistent`` is False."""

    def __init__(self, user: str | None):
        self.user = user
        self.persistent = shortlist.storage_configured()

    def _cache(self) -> dict:
        return st.session_state.setdefault(_CACHE, {}).setdefault(self.user or "", {})

    def get(self, key: str, default=None):
        cache = self._cache()
        if key not in cache and self.persistent:
            try:
                part = shortlist.scope(shortlist._read_all(), self.user)
                cache[key] = copy.deepcopy(part[key]) if key in part else _MISSING
            except Exception:  # network / auth: keep working on this session's copy
                self.persistent = False
        value = cache.get(key, _MISSING)
        return default if value is _MISSING else copy.deepcopy(value)

    def set(self, key: str, value) -> bool:
        """Store ``value``; True if it was saved beyond this session."""
        self._cache()[key] = copy.deepcopy(value)
        if not self.persistent:
            return False
        try:
            doc = shortlist._read_all()
            shortlist.scope(doc, self.user)[key] = value
            shortlist._write_all(doc)
            return True
        except Exception:
            return False


# ---- Streamlit side -----------------------------------------------------------------------


def oidc_enabled() -> bool:
    """Google sign-in only when it is configured AND usable (st.login needs Authlib)."""
    try:
        if "auth" not in st.secrets:
            return False
        import authlib  # noqa: F401
    except Exception:  # no secrets file at all, or Authlib missing: PIN profiles instead
        return False
    return True


def _google_user() -> tuple[str, str] | None:
    """(key, display name) of the Google-signed-in user, if any."""
    if not oidc_enabled():
        return None
    try:
        user = st.user
        if not user.get("is_logged_in"):
            return None
        email = user.get("email") or ""
        return f"google:{email.casefold()}", user.get("name") or email
    except Exception:
        return None


def current_user() -> str | None:
    """The signed-in profile key, or None (anonymous)."""
    g = _google_user()
    return g[0] if g else st.session_state.get(SESSION_KEY)


def display_name() -> str | None:
    g = _google_user()
    return g[1] if g else st.session_state.get("profile_name")


def storage() -> Store:
    return Store(current_user())


def _forget_session_copies() -> None:
    for k in _SESSION_CACHES:
        st.session_state.pop(k, None)


def _restore_last_page() -> None:
    page = storage().get("last_page")
    if page:
        st.session_state["account_restore_page"] = page


def remember_page(page: str) -> None:
    """Keep the signed-in user's last page (written only when it changes)."""
    if current_user() and storage().get("last_page") != page:
        storage().set("last_page", page)


def _sign_in(key: str, name: str) -> None:
    _forget_session_copies()
    st.session_state[SESSION_KEY] = key
    st.session_state["profile_name"] = name
    st.session_state.pop("login_pin", None)
    _restore_last_page()


def _do_login(create: bool) -> None:
    name = st.session_state.get("login_name", "")
    pin = st.session_state.get("login_pin", "")
    try:
        key = create_profile(name, pin) if create else check_pin(name, pin)
    except ProfileError as e:
        st.session_state["login_msg"] = str(e)
        return
    except Exception:
        st.session_state["login_msg"] = "Η σύνδεση δεν είναι διαθέσιμη αυτή τη στιγμή."
        return
    prof = shortlist._read_all().get("profiles", {}).get(key, {})
    st.session_state.pop("login_msg", None)
    _sign_in(key, prof.get("name") or name.strip())


def logout() -> None:
    _forget_session_copies()
    for k in (SESSION_KEY, "profile_name", "login_msg"):
        st.session_state.pop(k, None)
    if _google_user():
        st.logout()


SESSION_ONLY = "Χωρίς σύνδεση: οι επιλογές σου μένουν μόνο σε αυτή την καρτέλα."
NOT_SIGNED_IN = "Χωρίς σύνδεση — συνδέσου για να κρατηθούν οι επιλογές σου στο δικό σου προφίλ."


def login_ui() -> None:
    """Sidebar block: «Συνδεδεμένος ως …» + «Αποσύνδεση», or the way to sign in."""
    name = display_name()
    if name:
        st.markdown(f"Συνδεδεμένος ως **{name}**")
        st.button("Αποσύνδεση", key="logout", on_click=logout, width="stretch")
        return
    if oidc_enabled():
        st.caption("Σύνδεση για να κρατηθούν τα αγαπημένα και οι απαντήσεις σου.")
        if st.button("Σύνδεση με Google", key="login_google", width="stretch"):
            st.login()
        return
    if not shortlist.storage_configured():
        st.caption(SESSION_ONLY)
        return
    # Streamlit's own field hint («Press Enter to apply») is English: hide it in the sidebar.
    st.markdown(
        "<style>section[data-testid='stSidebar'] [data-testid='InputInstructions']"
        "{display:none}</style>",
        unsafe_allow_html=True,
    )
    with st.expander("Σύνδεση", expanded=bool(st.session_state.get("login_msg"))):
        st.text_input("Όνομα", key="login_name", max_chars=40)
        st.text_input("PIN (4 ψηφία)", key="login_pin", type="password", max_chars=4)
        c1, c2 = st.columns(2)
        c1.button("Σύνδεση", key="login_go", on_click=_do_login, args=(False,), width="stretch")
        c2.button("Νέο προφίλ", key="login_new", on_click=_do_login, args=(True,), width="stretch")
        if st.session_state.get("login_msg"):
            st.warning(st.session_state["login_msg"])
        st.caption("Το PIN προστατεύει μόνο τις προτιμήσεις σου σε αυτή την εφαρμογή.")
    st.caption(NOT_SIGNED_IN)


# Every shortlist call (favourites, verdicts, saved searches) acts on the signed-in user.
shortlist.profile_hook = current_user
