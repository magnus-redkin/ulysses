# Threat Classification

Everything around censorship circumvention falls into two major categories. It's important not to confuse them, because they require different tools.

## Local Threats (from the state/censor)

This is what's commonly called "blocking." The state tries to cut you off from the outside world at the backbone level. They see your traffic at the country's ingress/egress points and decide whether to let it through.

Countermeasures include traffic masking to make it look like regular HTTPS, SNI spoofing, and wrappers like Reality and ShadowTLS. It's an endless cat-and-mouse game: the censor updates DPI, protocol developers add new obfuscation. The cycle is short, changes are fast.

Treat this as an inevitable technical process. It's neither good nor bad — it's just a reality you work with.

## Global Threats (from corporations and the infrastructure itself)

This is a different story. Google, Meta, your ISP, your browser, installed apps — they collect data about you constantly. Not to block you, but to sell or analyze it.

This is harder to deal with. Local threats you bypass technically — switch protocols, and you're done. Global threats aren't fixed by changing VPN servers. Because the very protocols you use for circumvention (TLS, QUIC, HTTP/3) are developed by these same corporations and contain metadata that can be analyzed.

The only defense is consciously reducing your digital footprint: fewer accounts, fewer extensions, control over what and when gets transmitted. But there's no 100% protection — you're still using their infrastructure.

---

**Summary:**

- **Local threats** — technical, solved by configuring protocols and servers.
- **Global threats** — behavioral and infrastructural, solved by changing habits and software choices.

They operate simultaneously. A good VPN saves you from the first, but not the second. In the following chapters, we'll cover tools for each case.
