## UDP-Oriented High-Speed Protocols

These protocols operate over UDP and use QUIC. Their main advantage is high speed and the ability to work in poor network conditions.

---

### Hysteria2

One of the most popular circumvention protocols. Built on QUIC (Google's modified UDP).

**Key feature:** an aggressive congestion control algorithm. Regular protocols sharply drop speed when packets are lost. Hysteria2 continues sending data at maximum speed — effectively punching through poor channels and ISP throttling.

**In version 2:**
- Full masking as standard HTTP/3 traffic.
- Built-in header obfuscation.
- Protection against active port scanning.

**When to use:** when the channel is unstable, with high packet loss, or when the ISP is throttling traffic. Works great on mobile networks.

---

### TUIC (version 5)

A high-speed proxy protocol on QUIC.

**Unlike Hysteria**, TUIC doesn't try to aggressively flood the channel with packets. Instead, it relies on minimalism:

- Combines user authentication and data transmission into a single step.
- Minimal RTT count for connection establishment.
- Very low latency (ping) when opening new sites.

TUIC v5 handles frequent IP changes on mobile devices gracefully — sessions don't break when switching between cell towers or Wi-Fi.

**When to use:** when minimal latency and stability during network switching are critical. Particularly good on mobile devices.

---

### WireGuard

A classic network-layer VPN protocol. Runs inside the OS kernel. Very fast and secure.

**But there's a problem:** WireGuard has no masking capabilities. Its standard packets are detected and blocked by DPI within seconds.

**So why is it in Hiddify-Manager?**

WireGuard isn't used for circumvention, but for an internal task: connecting the server to Cloudflare WARP. This allows:
- Routing server traffic through Cloudflare's clean IP addresses.
- Bypassing Google CAPTCHAs.
- Accessing services with regional restrictions (Netflix, ChatGPT).

So WireGuard here is a utility tool, not a primary client protocol.

**When to use:** only if you need to solve CAPTCHA or regional restriction issues via WARP. Not for regular circumvention.

---

### What and When to Use

| Protocol | Key Feature | When to Use |
|:--------|:--------|:------------|
| **Hysteria2** | Breaks through poor channels, aggressive congestion control | Unstable network, high packet loss, mobile internet |
| **TUIC** | Minimal latency, stable during IP changes | Mobile devices, latency-sensitive apps |
| **WireGuard** | Speed, kernel-level operation | Only for WARP (CAPTCHAs, regional blocks) |
