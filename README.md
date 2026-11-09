# Ayoub SSH Manager (prototype)

Color terminal menu for **Ubuntu 24.04** with OpenSSH user accounts and Xray VMess/VLESS/Trojan over WebSocket/TLS behind Caddy.

## Install from GitHub

On a **fresh VPS**, verify the script source and run:

```bash
curl -fLsS https://raw.githubusercontent.com/ayoubgb19/ayoub-ssh-manager/main/install.sh -o /tmp/ayoub-install.sh
sudo bash /tmp/ayoub-install.sh
```

Then run `sudo menu`.

**Important:** setup prompts for the domain and confirmation; it installs and reconfigures SSH bridge, Xray and Caddy, backing up their existing configuration. Domain DNS A record must match VPS public IPv4. TCP 80/443 must be reachable.

**Not implemented:** Real enforcement of IP limit / GB quota, gRPC, non-TLS, OpenVPN, UDP, Dropbear, SlowDNS, OpenClash links, full screenshot feature parity. This prototype is **not production-tested** on a VPS. Verify code before running as root.
