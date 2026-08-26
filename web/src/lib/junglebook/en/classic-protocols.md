## Classic and Application-Layer Proxy Protocols

---

### VLESS

A modern lightweight application-layer protocol, the industry standard.

**Key feature:** it has no built-in encryption. The developers removed it from the code to reduce CPU load on both server and client. Security is provided by an external layer — TLS certificate or Reality.

Authorization is based on a unique UUID.

In Hiddify-Manager, VLESS is a universal constructor. It supports all transport types: TCP, WebSockets, gRPC, HTTPUpgrade, XHTTP.

**When to use:** anywhere you need flexibility and minimal overhead. The default choice for most scenarios.

---

### VMess

The historical predecessor of VLESS from the V2Ray ecosystem.

**Key feature:** built-in encryption for every packet. This provides protection out of the box, but adds CPU overhead.

**Problem:** modern DPI systems have learned to identify the structure of VMess encrypted headers. The protocol is vulnerable to active probing.

In Hiddify-Manager, VMess is used primarily for compatibility with legacy clients. Alternatively, it's wrapped in WebSockets or gRPC over CDN.

**When to use:** only for compatibility with legacy software. For new projects — use VLESS.

---

### Trojan

A masking protocol designed with one simple idea: to become indistinguishable from regular HTTPS traffic.

**How it works:**

- Operates exclusively inside a full TLS tunnel over TCP.
- The client sends a password in the first packet within the TLS session.
- If the password is correct — the server opens a proxy tunnel.
- If not — the server pretends to be a regular website and serves an innocuous page.

The censor sees valid HTTPS data exchange — nothing suspicious.

**When to use:** when you need reliable masking as regular web traffic. Works particularly well through CDN (Cloudflare).

---

### Shadowsocks (AEAD and 2022)

A legendary protocol, battle-tested over years.

**Modern versions:**
- **AEAD** — uses authenticated encryption, protects packets from on-the-fly modification.
- **Shadowsocks-2022** — completely redesigned fixed-length headers. DPI has nothing to latch onto.

The protocol is fast, consumes minimal resources, and is ideal for routers.

In Hiddify-Manager, it's often combined with obfuscation plugins to evade blocking.

**When to use:** when maximum speed and minimal resource consumption are critical. An excellent choice for low-power devices (routers, older smartphones).

---

### Mieru

A specialized protocol designed to counter active probing and DPI.

**Philosophy:** minimal logging and complete unpredictability.

**How it works:**
- Aggressive randomization of packet lengths and intervals between them.
- Destroys the statistical traffic analysis models used by censors.
- The server behaves extremely quietly — it doesn't reveal its presence at all.

Mieru doesn't try to masquerade as a specific protocol. Instead, it makes its traffic maximally chaotic, so DPI cannot build a pattern.

**When to use:** under aggressive censorship when other protocols are already detected. An experimental option for the most complex scenarios.

---

### What and When to Use

| Protocol | When to Use |
|:--------|:------------|
| **VLESS** | Default choice. Flexible, lightweight, supports all transports. |
| **VMess** | Only for compatibility with legacy clients. |
| **Trojan** | When you need masking as regular HTTPS. Works well through CDN. |
| **Shadowsocks** | When speed and minimal resource usage matter. Ideal for routers. |
| **Mieru** | In the most challenging environments with total UDP and TCP traffic filtering. |
