# Accounts — who is using the app, and where their preferences live

Code: `src/scout/ui/account.py` (UI + API), `src/scout/shortlist.py` (the stored document).

A signed-in person finds their **favourites (Αγαπημένα), approve/drop verdicts, saved searches and
guide answers** where they left them, on any device.

## Two ways to sign in (one API)

| Configured? | What the sidebar shows | Profile key |
|---|---|---|
| Streamlit secrets have an `[auth]` section | «Σύνδεση με Google» → `st.login()` | `google:<email>` |
| Otherwise, `GITHUB_TOKEN` is set | «Σύνδεση» expander: «Όνομα» + 4-digit PIN, «Σύνδεση» / «Νέο προφίλ» | the name, lower-case, no accents |
| Neither | one line: «Χωρίς σύνδεση: οι επιλογές σου μένουν μόνο σε αυτή την καρτέλα.» | — |

Signed in, the sidebar shows «Συνδεδεμένος ως …» and «Αποσύνδεση».

Other pages use:

```python
from scout.ui import account
account.current_user()          # profile key or None (anonymous)
store = account.storage()       # per-user store
store.get("guide", {})          # e.g. the guide's answers
store.set("guide", answers)     # True if saved beyond this session
```

`shortlist.watch_set/set_watch/review_map/set_review/*_mandate` act on the signed-in user
automatically (`shortlist.profile_hook` points at `account.current_user`).

## Turning on Google sign-in (owner, once)

1. Google Cloud Console → APIs & Services → Credentials → **Create OAuth client ID** →
   type *Web application*. Under **Authorized redirect URIs** add exactly:
   `https://xescout.streamlit.app/oauth2callback`
   (OAuth consent screen: type *External*; add your own Google address as a test user, or
   publish the app.)
2. Generate a cookie secret: `python -c "import secrets; print(secrets.token_hex(32))"`.
3. Streamlit Community Cloud → the app → **Settings → Secrets**, add (keep the existing
   `DATABASE_URL` / `GITHUB_TOKEN` / `ANTHROPIC_API_KEY` lines):

```toml
[auth]
redirect_uri = "https://xescout.streamlit.app/oauth2callback"
cookie_secret = "<the 64-character hex string from step 2>"
client_id = "<…>.apps.googleusercontent.com"
client_secret = "<client secret from step 1>"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

4. Save; the app restarts. The sidebar now shows «Σύνδεση με Google». `Authlib` (required by
   `st.login`) is in `pyproject.toml`; if it is ever missing the app falls back to PIN profiles
   instead of failing.

To turn Google sign-in off, delete the `[auth]` section.

## PIN profiles

- Stored in the private gist document (`mandates.json`) as
  `profiles[key] = {"name", "salt", "hash", "fails", "locked_until", "data": {...}}`.
- `hash = sha256(salt + pin)` with a random 16-byte `salt` per profile. The PIN itself is
  never stored, logged or shown; the PIN field is a password field.
- 5 wrong PINs lock that name for 10 minutes. The counter and lock time are in the gist, so a
  new tab or device does not reset them.

**What the PIN protects — and what it does not.** The gist is private to the owner's GitHub
token, and only the app reads it. The PIN only keeps one person's *preferences* (favourites,
verdicts, saved searches, answers) apart from another's inside this app. It is not a bank
password: a 4-digit PIN can be guessed with patience (the lockout slows that down), and the app
says whether a name exists. Don't reuse a PIN you use elsewhere; nothing sensitive is stored.
For real identity, turn on Google sign-in.

## Nothing already saved is lost

- The gist's top-level `mandates` / `watch` / `review` keys — everything saved before
  accounts existed — are the **anonymous profile**: what you see while not signed in, exactly
  as before.
- The **first PIN profile created** starts with a copy of those anonymous favourites, verdicts
  and saved searches (the owner is the first to sign up, so their choices follow them). The
  anonymous copy stays where it was. Later profiles start empty.
- The daily digest (`shortlist.run_shortlists`) sends saved-search digests for every profile,
  anonymous included.
