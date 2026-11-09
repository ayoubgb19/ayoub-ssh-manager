#!/usr/bin/env bash
set -Eeuo pipefail
[[ ${EUID} -eq 0 ]] || { echo "Run as root: sudo bash setup.sh"; exit 1; }
[[ -f /etc/os-release ]] || { echo "Ubuntu 24.04 is required"; exit 1; }
. /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == "24.04" ]] || { echo "Ubuntu 24.04 required"; exit 1; }
SOURCE="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/manager.py}"
[[ -f "$SOURCE" ]] || { echo "manager.py missing: $SOURCE"; exit 1; }
echo "WARNING: Installs packages and REPLACES Caddy/Xray configuration; use a fresh VPS."
read -r -p "Continue? [y/N]: " yes
[[ "$yes" =~ ^[Yy]$ ]] || exit 0
read -r -p "Domain with DNS A record pointing to VPS: " DOMAIN
[[ "$DOMAIN" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ && "$DOMAIN" == *.* ]] || { echo "Invalid domain"; exit 1; }
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y curl ca-certificates gnupg python3 python3-venv openssh-server dnsutils unzip
IP="$(curl -4fsS --max-time 10 https://api.ipify.org)"
DNS="$(dig +short A "$DOMAIN")"
echo "VPS IPv4: $IP"
echo "DNS IPv4: $DNS"
grep -Fxq "$IP" <<< "$DNS" || { echo "Domain DNS does not resolve to VPS public IPv4"; exit 1; }
install -d -m 755 /run/sshd
/usr/sbin/sshd -t
systemctl enable --now ssh.service || systemctl enable --now ssh.socket
apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
curl -fLsS https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --batch --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -fLsS https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt -o /etc/apt/sources.list.d/caddy-stable.list
apt-get update
apt-get install -y caddy
xrayinstaller="$(mktemp)"
trap 'rm -f "$xrayinstaller"' EXIT
curl -fLsS https://github.com/XTLS/Xray-install/raw/main/install-release.sh -o "$xrayinstaller"
bash "$xrayinstaller" install
install -d -m 700 /etc/ayoub-new-manager
DOMAIN="$DOMAIN" python3 - <<'PY'
import os,json,pathlib
root=pathlib.Path('/etc/ayoub-new-manager')
p=root/'settings.json'
p.write_text(json.dumps({'domain':os.environ['DOMAIN']},indent=2)+'\n')
p.chmod(0o600)
db=root/'accounts.json'
if not db.exists():
 db.write_text(json.dumps({k:{} for k in ('ssh','vmess','vless','trojan')},indent=2)+'\n')
db.chmod(0o600)
PY
python3 -m py_compile "$SOURCE"
install -m 755 "$SOURCE" /usr/local/bin/ayoub-new-manager
python3 -m venv /opt/ayoub-new-websocket
/opt/ayoub-new-websocket/bin/pip install --disable-pip-version-check websockify
cat > /etc/systemd/system/ssh-websocket.service <<'UNIT'
[Unit]
Description=Ayoub SSH WebSocket bridge
After=network-online.target ssh.service
Wants=network-online.target
[Service]
Type=simple
ExecStart=/opt/ayoub-new-websocket/bin/websockify 127.0.0.1:2080 127.0.0.1:22
Restart=always
RestartSec=3
NoNewPrivileges=true
[Install]
WantedBy=multi-user.target
UNIT
stamp="$(date +%Y%m%d-%H%M%S)"
[[ ! -f /etc/caddy/Caddyfile ]] || cp -a /etc/caddy/Caddyfile "/etc/caddy/Caddyfile.bak.$stamp"
caddy_tmp="$(mktemp --suffix=.Caddyfile)"
trap 'rm -f "$xrayinstaller" "$caddy_tmp"' EXIT
cat > "$caddy_tmp" <<EOF
$DOMAIN {
 @ssh path /ssh
 handle @ssh {
  reverse_proxy 127.0.0.1:2080
 }
 @vmess path /vmess
 handle @vmess {
  reverse_proxy 127.0.0.1:10001
 }
 @vless path /vless
 handle @vless {
  reverse_proxy 127.0.0.1:10002
 }
 @trojan path /trojan
 handle @trojan {
  reverse_proxy 127.0.0.1:10003
 }
 respond "Ayoub SSH Manager" 200
}
EOF
caddy validate --adapter caddyfile --config "$caddy_tmp"
xray_tmp="$(mktemp --suffix=.json)"
trap 'rm -f "$xrayinstaller" "$caddy_tmp" "$xray_tmp"' EXIT
python3 - "$xray_tmp" <<'PY'
import sys,json
from importlib.machinery import SourceFileLoader
m=SourceFileLoader('ayoub','/usr/local/bin/ayoub-new-manager').load_module()
with open(sys.argv[1],'w') as f: json.dump(m.xray_config(m.db()),f,indent=2)
PY
/usr/local/bin/xray run -test -config "$xray_tmp"
install -m 644 "$caddy_tmp" /etc/caddy/Caddyfile
xr=/usr/local/etc/xray/config.json
mkdir -p /usr/local/etc/xray
[[ ! -f "$xr" ]] || cp -a "$xr" "$xr.bak.$stamp"
install -m 644 "$xray_tmp" "$xr"
cat > /usr/local/bin/menu <<'MENU'
#!/bin/sh
exec python3 /usr/local/bin/ayoub-new-manager "$@"
MENU
chmod 755 /usr/local/bin/menu
systemctl daemon-reload
systemctl enable --now ssh-websocket xray caddy
systemctl restart ssh-websocket xray caddy
printf '\nInstalled. Run: sudo menu\n'
echo "Important: check SSH password authentication policy; default 22/TCP, HTTPS 443/TCP and ACME 80/TCP."
echo "Quota/IP limits are NOT enforced. No gRPC, non-TLS, OpenVPN or Dropbear yet."
echo "This prototype has not been tested end-to-end on a real VPS."
