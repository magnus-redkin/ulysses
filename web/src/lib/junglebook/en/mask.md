## Traffic Masking and Protection Technologies

These technologies are not standalone protocols. They work on top of primary protocols (VLESS, Shadowsocks) and hide the very fact that a proxy is being used.

---

### Reality (XTLS)

A masking technology for VLESS and XHTTP transport. Solves the main problem — the need to buy and renew your own domains and TLS certificates.

**How it works:**

Your server doesn't use its own certificate. Instead, it "borrows" the identity of a major legitimate site (Apple, Microsoft, Samsung).

- When the censor scans your IP, the server forwards the request to the real donor site.
- The censor sees a valid TLS handshake with a trusted resource — nothing suspicious.
- The client with the correct key intercepts the session and enters the proxy tunnel.

**Result:** perfect masking without your own domain or certificate.

**When to use:** whenever maximum masking is needed without extra costs. Reality is the modern standard.

---

### ShadowTLS

A wrapper layer for masking Shadowsocks.

**How it works:**

ShadowTLS simulates a legitimate TLS connection to a chosen popular site. Unlike Reality, here there is an actual handshake with a real donor server. Proxy data is mixed into this secure stream.

To DPI, such a connection looks like a regular user visit to a trusted web resource.

**When to use:** if you're using Shadowsocks and want to hide it from DPI. An alternative to Reality for those who, for whatever reason, stick with Shadowsocks.

---

### Reality vs ShadowTLS

| | Reality | ShadowTLS |
|:--------|:--------|:-----------|
| For which protocols | VLESS, XHTTP | Shadowsocks |
| Requires own domain | No | No |
| How it masks | "Borrows" donor site identity | Simulates real TLS handshake with donor |
| Setup complexity | Medium | Medium |
| When to use | Modern standard for VLESS | When you need masking specifically for Shadowsocks |

---

**Summary:** Reality is a more universal and modern solution. ShadowTLS is an option for those who are tied to Shadowsocks for some reason and want to protect it.
