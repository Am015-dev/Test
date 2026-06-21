# Free custom domain + HTTPS for the dashboard

Turns `http://<public-ip>:8501` into `https://yourname.duckdns.org`. Everything here is
free. Uses **DuckDNS** (free subdomain) + the **Caddy** reverse proxy already wired into
`docker-compose.yml` (auto Let's Encrypt certificate, renewed automatically).

## What you do (3 manual steps — they need your account / the OCI console)

1. **Get a free subdomain** at <https://www.duckdns.org> (sign in with GitHub/Google).
   Create e.g. `holargos`, and set its IP to this server's **public IP**. You now own
   `holargos.duckdns.org`. (Oracle Always-Free IPs are effectively static; if yours ever
   changes, re-point it on the DuckDNS page or run their updater.)

2. **Open the ports in the OCI console** (the in-VM `iptables` is handled by cloud-init,
   but the cloud firewall is separate): VCN → Security List (or the instance's NSG) → add
   **Ingress** rules allowing TCP **80** and **443** from `0.0.0.0/0`.

3. **Tell the app the domain**: on the instance, add to `/opt/holargos/.env`:
   ```
   SITE_ADDRESS=holargos.duckdns.org
   ```

## Start it

```bash
cd /opt/holargos && docker compose --profile proxy up -d
```

Caddy starts on 80/443, fetches a free certificate for the domain, and reverse-proxies to
Streamlit. Visit **https://holargos.duckdns.org** — real HTTPS, no port, no raw IP.

## Lock it down (recommended — the dashboard has no login)

Once public, anyone with the URL can view your data. Add a password:

```bash
# generate a hash
docker run --rm caddy:2-alpine caddy hash-password --plaintext 'choose-a-password'
```

Uncomment the `basic_auth` block in `Caddyfile`, paste the hash, then
`docker compose --profile proxy up -d` again. (Or keep it private instead — see below.)

## Notes
- You can stop exposing the raw port: remove the `8501:8501` ports mapping from the `web`
  service so the dashboard is reachable only through Caddy/HTTPS.
- If Streamlit's live updates misbehave behind the proxy, add
  `--server.enableCORS=false --server.enableXsrfProtection=false` to `scripts/start.sh`
  (try the defaults first — Caddy upgrades WebSockets automatically).

## Private alternative (also free, most secure): Tailscale

If only you need access, skip DuckDNS/Caddy/ports entirely:
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
sudo tailscale serve https / http://localhost:8501
```
Gives a stable `https://<host>.<tailnet>.ts.net` reachable only from your tailnet devices —
free, automatic HTTPS, no open ports, private by construction.
