#!/usr/bin/env bash
# One-shot setup for an Oracle Cloud Always Free instance (Ubuntu 22.04).
# Recommended shape: VM.Standard.A1.Flex (Ampere ARM), 2+ OCPUs, 6+ GB RAM.
#
# The repo is PRIVATE, so cloning needs a read-only GitHub token. Provide it via
# the GITHUB_TOKEN env var (a classic token with `repo` scope, or a fine-grained
# token with Contents:Read on Am015-dev/Test):
#
#   export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
#   git clone https://$GITHUB_TOKEN@github.com/Am015-dev/Test.git holargos
#   GITHUB_TOKEN=$GITHUB_TOKEN bash holargos/deploy/oracle-setup.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"
if [ -n "$GITHUB_TOKEN" ]; then
    REPO_URL="https://${GITHUB_TOKEN}@github.com/Am015-dev/Test.git"
else
    # Falls back to unauthenticated (works only if the repo is public).
    REPO_URL="https://github.com/Am015-dev/Test.git"
fi
INSTALL_DIR="/opt/holargos"

echo "=== Holargos Property Scout — Oracle Cloud setup ==="

# ── 1. Docker ────────────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo "[1/6] Installing Docker..."
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER"
    echo "      Docker installed. If this is your first run you may need to"
    echo "      log out and back in so group membership takes effect, then"
    echo "      re-run this script."
else
    echo "[1/6] Docker already installed — skipping."
fi

# ── 2. Clone / update repo ───────────────────────────────────────────────────
echo "[2/6] Cloning / updating repo to $INSTALL_DIR..."
sudo mkdir -p "$INSTALL_DIR"
sudo chown "$USER":"$USER" "$INSTALL_DIR"
if [ -d "$INSTALL_DIR/.git" ]; then
    git -C "$INSTALL_DIR" pull origin main
else
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

# ── 3. Environment file ──────────────────────────────────────────────────────
echo "[3/6] Environment file..."
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    echo ""
    echo "  ⚠️  Please edit $INSTALL_DIR/.env before the first run:"
    echo "      nano $INSTALL_DIR/.env"
    echo ""
    echo "  At minimum set GEOCODER_USER_AGENT to your own contact address,"
    echo "  e.g.  GEOCODER_USER_AGENT=holargos-scout/1.0 (you@example.com)"
    echo ""
    read -rp "  Press Enter once you've saved the file..." _
else
    echo "      .env already exists — skipping."
fi

# ── 4. Build image and start Streamlit ───────────────────────────────────────
echo "[4/6] Building Docker image and starting Streamlit (this may take a few minutes)..."
cd "$INSTALL_DIR"
docker compose up -d --build
echo "      Container started."

# ── 5. Daily cron job ────────────────────────────────────────────────────────
echo "[5/6] Installing daily pipeline cron job (06:00 UTC)..."
CRON_CMD="cd $INSTALL_DIR && docker compose run --rm web bash -c 'python scripts/enqueue.py && python scripts/worker.py' >> /var/log/holargos-daily.log 2>&1"
CRON_LINE="0 6 * * * $CRON_CMD"
# Remove any existing holargos cron line, then add the fresh one.
( crontab -l 2>/dev/null | grep -v "holargos" ; echo "$CRON_LINE" ) | crontab -
echo "      Cron installed: $CRON_LINE"

# ── 6. Firewall ──────────────────────────────────────────────────────────────
echo "[6/6] Opening port 8501 in iptables..."
sudo iptables -I INPUT -p tcp --dport 8501 -j ACCEPT
# Persist across reboots (iptables-persistent may not be installed; best-effort).
if command -v iptables-save &>/dev/null; then
    sudo iptables-save | sudo tee /etc/iptables/rules.v4 > /dev/null 2>&1 || true
fi

PUBLIC_IP="$(curl -s --max-time 5 ifconfig.me 2>/dev/null || echo '<public-ip>')"

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║  Setup complete!                                                 ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
echo "  Streamlit UI:  http://${PUBLIC_IP}:8501"
echo "  Daily pipeline: 06:00 UTC via cron (logs → /var/log/holargos-daily.log)"
echo ""
echo "  ⚠️  You still need to open port 8501 in the OCI Security List:"
echo "      OCI Console → Networking → Virtual Cloud Networks"
echo "      → your VCN → Security Lists → Default → Add Ingress Rule"
echo "      Source CIDR: 0.0.0.0/0   Protocol: TCP   Port: 8501"
echo ""
echo "  To trigger the first scrape now:"
echo "      cd $INSTALL_DIR && docker compose run --rm web python scripts/run_daily.py"
echo ""
