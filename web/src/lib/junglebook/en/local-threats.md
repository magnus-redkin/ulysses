## Threats from State Censors (Backbone Control)

These threats are developed by state structures within the framework of "sovereign internet" concepts. Their goal is to gain full control over cross-border traffic and enable isolation of the national network segment.

### 1. AI-Driven Active Probing

**Technical essence:**
DPI (Deep Packet Inspection) systems don't just passively analyze packets — they automatically send complex, neural-network-generated probes to suspicious ports on your VPS. These probes mimic the behavior of various operating systems and specific clients.

**Threat description:**
Current masking technologies (Reality, ShadowTLS) successfully respond to basic scanner requests. However, an AI-powered censor can conduct a lengthy "dialogue" with a port, checking its response to rare network errors, non-standard flags, or specific TLS extensions (e.g., differences in TLS fingerprinting mechanisms). If your VPS responds even once differently from the original donor site, the server is immediately blocked.

---

### 2. Shift to Strict "Whitelisting" (Whitelist Default)

**Technical essence:**
A radical change in the logic of TSPU (technical means of counteracting threats). Instead of blocking prohibited sites, the censor blocks all foreign traffic by default, except for a narrow list of approved IP addresses, autonomous systems (AS), and domains.

**Threat description:**
This makes purchasing a personal VPS ineffective — its IP address is blocked from the start because it's not in the state registry of permitted foreign resources. Circumvention protocols are forced to migrate inside the traffic of major approved corporations (Google, Cloudflare, Microsoft) and use CDNs. This shifts the battle into the realm of header warfare, SNI fronting, and tunneling inside legitimate web services.

---

### 3. Artificial UDP Degradation (UDP Throttling and Packet Loss Injection)

**Technical essence:**
Intentional bandwidth limitation or artificial generation of high packet loss (up to 50–70%) for all unrecognized UDP traffic (or traffic not belonging to known corporate VPNs) on cross-border links.

**Threat description:**
This method targets the effectiveness of next-generation protocols — Hysteria2 and TUIC. Despite QUIC protocols being optimized for unstable channels, when artificial losses exceed a critical level, connection speed drops to zero. Constant delays and retransmissions make web surfing impossible.

---

### 4. Forced Stripping of TLS SNI / War on ECH (Encrypted Client Hello)

**Technical essence:**
Blocking or forcibly terminating any TLS connections that attempt to use ECH (encryption of the target server name in the initial Client Hello packet), or blocking sessions where the SNI field is absent or encrypted in a non-standard way.

**Threat description:**
State censors preemptively ban technologies that deprive them of visibility into the target website name. This forces proxy developers to continuously use only open TLS 1.3 with SNI spoofing to approved resources (as in Reality). In the long term, this leaves censors with a mathematical advantage for behavioral and statistical analysis of such sessions.

---

**Summary:**
State censors are moving from simple IP blocking to intelligent, adaptive methods. AI-driven probing, whitelisting, UDP degradation, and anti-ECH measures form a multi-layered system designed to make circumvention technically and economically unsustainable.
