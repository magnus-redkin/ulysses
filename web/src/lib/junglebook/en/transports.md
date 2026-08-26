## Network Transports and Wrappers

Authentication protocols (VLESS, VMess) can't transmit data on their own. They need a transport container — a wrapper that carries traffic from client to server.

---

### TCP

The standard base transport. Fastest and simplest.

**Problem:** easily analyzed by DPI. If used without additional masking, traffic is detected and blocked.

**When to use:** only if you're certain your ISP doesn't use active DPI, or in combination with other technologies (Reality). Otherwise — no.

---

### WebSockets (WS)

Wraps traffic in standard HTTP requests.

**Main advantage:** ideal for working through CDN (Cloudflare). The censor only sees a connection to Cloudflare — your real VPS remains hidden.

**Downsides:** slightly higher latency than plain TCP.

**When to use:** if you're using CDN to mask your server's IP.

---

### gRPC

A modern transport from Google for microservice communication. Runs over HTTP/2.

**Features:**
- Creates a single persistent tunnel for all data.
- Specific packet structure helps bypass behavioral DPI blocking.

**When to use:** when you need reliable transport with low detection probability. Particularly good in corporate networks.

---

### HTTPUpgrade

A lightweight alternative to WebSockets. Faster than WS, but does almost the same thing — wraps traffic in HTTP requests.

**When to use:** when you need CDN-based operation but with lower latency than WebSockets.

---

### xHTTP

The newest transport for bypassing the most sophisticated blocks.

**The problem with regular transports:** WebSockets and others create predictable two-way connections. DPI sees this and can identify the proxy.

**How xHTTP solves it:**
- Splits traffic, mimicking standard browser behavior.
- Dynamically changes headers.
- Separates inbound and outbound streams into different HTTP sessions.

To DPI, this looks like a regular set of user requests to a website, not a proxy tunnel.

**When to use:** under aggressive censorship when other transports are already detected. An experimental but powerful option.

---

### What and When to Use

| Transport | Key Feature | When to Use |
|:--------|:--------|:------------|
| **TCP** | Fast, simple | Only with Reality or if DPI is inactive |
| **WebSockets** | CDN operation, hides server IP | If using Cloudflare for masking |
| **gRPC** | Persistent tunnel, bypasses behavioral DPI | In corporate networks, under heavy DPI |
| **HTTPUpgrade** | Like WS, but faster | When you need CDN with lower latency |
| **xHTTP** | Breaks DPI patterns, splits streams | In the toughest conditions when nothing else works |
