## Auxiliary and Built-in Services

These are not primary circumvention protocols, but additional tools built into Hiddify-Manager. They solve specific tasks: backup channel, Telegram configuration, DNS query protection.

---

### SSH Proxy

A classic tunneling method. Every Linux server has an open SSH port for administration. Hiddify-Manager allows using the same port for proxy channels (SOCKS5/HTTP).

**Features:**
- No advanced masking — DPI easily detects SSH traffic.
- No additional configuration required if SSH is already open.

**When to use:** as a backup channel. If the main cores (Sing-box, Xray) are temporarily down for maintenance, the SSH proxy remains working. This is insurance, not a primary tool.

---

### MTProto (Telegram Proxy)

A specialized protocol for bypassing censorship in Telegram. Developed by the messenger's team.

**How it works:**
- Hiddify-Manager includes a built-in MTProto server implementation.
- It runs independently from the main proxy core (Sing-box/Xray).
- The output is a ready-made link — you can paste it directly into Telegram without additional VPN clients.

**When to use:** when you need to quickly set up Telegram access for others or on devices where installing a full VPN is inconvenient.

---

### DNS over HTTPS (DoH)

A secure DNS protocol. Any circumvention becomes meaningless if your ISP can see which domains you're requesting through plain DNS queries.

**How it works:**
- DoH packages name resolution requests into standard HTTPS traffic.
- Sends them to trusted servers (Cloudflare, Google, AdGuard).

**What it provides:**
- Protection against DNS query interception.
- Protection against DNS spoofing (IP address substitution).
- Protection against covert filtering by your ISP.

**When to use:** always, if your ISP can intercept or filter your DNS queries. This is a basic security element, not an optional feature.

---

### What and When to Use

| Service | Key Feature | When to Use |
|:--------|:--------|:-------------------|
| **SSH Proxy** | Backup channel via SSH port | When main cores are temporarily down |
| **MTProto** | Proxy for Telegram, ready-made link | Quick Telegram access without clients |
| **DoH** | DNS query protection from ISP | Always, if your ISP controls DNS |
