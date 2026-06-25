# Deploy (Oracle Cloud Always-Free) — free, zero-SSH, self-healing

The instance tracks `main` on its own. All free: cloud-init + cron + git + docker compose.

## How it works

- **First boot** (`cloud-init.yaml`): installs Docker, clones the repo, runs
  `reconcile.sh`, builds, opens the firewall.
- **`reconcile.sh`** (the convergence step, run at boot AND every update tick): creates
  `.env` from `.env.example` and **appends any new keys** it's missing (without touching
  values you set), and **(re)installs the cron** (auto-update every 5 min, daily scrape
  06:00 UTC, healthcheck 07:00 & 19:00 UTC). Idempotent.
- **`auto-update.sh`** (cron, */5): runs `reconcile.sh`, then `git fetch`; if `main`
  moved it `reset --hard` + rebuilds; always `docker compose up -d` (honouring
  `COMPOSE_PROFILES` from `.env`, e.g. the Caddy HTTPS proxy). No-op when current.

Because `reconcile.sh` runs every tick, **config changes (new cron jobs, new `.env`
keys) land on already-running instances too** — the old "ships code but not cron/env"
drift is gone.

## What still needs you (one-time, free)

- **Switch to Postgres**: `reconcile.sh` now appends `DATABASE_URL` (the bundled `db`
  service) on the next tick, so the box converges to Postgres automatically. The DB
  starts empty and the next scrape repopulates it.
- **Secrets/opt-ins** are blank by default — set them in `/opt/holargos/.env`:
  `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` (digest), `SITE_ADDRESS` + `COMPOSE_PROFILES=proxy`
  (HTTPS domain), `FLARESOLVERR_URL` (WAF portals).
- **Open ports in the OCI console** (VCN Security List / NSG) for 80/443 if using the
  proxy — the in-VM firewall is handled, the cloud firewall is separate.

## Retrofit an OLDER instance (created before these changes)

SSH in once and pull + converge; from then on it self-updates:

```bash
cd /opt/holargos \
  && git fetch origin main && git reset --hard origin/main \
  && bash deploy/reconcile.sh \
  && docker compose up -d --build
```

If the auto-update cron was never installed, `reconcile.sh` installs it (so this is the
only manual step you'll ever need).

## Diagnose

```bash
tail -n 30 /var/log/holargos-update.log    # auto-update activity / "fetch failed"
crontab -l | grep '# holargos'             # the 3 installed jobs
git -C /opt/holargos rev-parse --short HEAD # compare to GitHub main
docker compose ps                          # running services
```

`fetch failed` means the GitHub token expired — update the remote URL in
`/opt/holargos/.git/config` with a fresh read-only token.
