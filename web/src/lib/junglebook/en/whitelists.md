## Whitelists: How VPNs Work in Full Isolation Mode

When ISPs enable "whitelist" mode (typically on mobile networks during emergencies or drone threats), all foreign traffic is blocked. Only a few hundred trusted Russian sites are allowed (government services, banks, VK, Yandex). Regular VPNs go completely blind at this moment — their foreign servers are immediately cut off.

However, commercial and private VPNs find ways to bypass this restriction by "piggybacking" on allowed traffic.

---

### Why Reality Doesn't Help with Whitelists

The Reality technology works by spoofing SNI. When you connect to a foreign VPN server, your phone sends a request saying: "I'm going to dl.google.com." The censor sees this name, checks it against the whitelist, sees Google there... and blocks the connection.

Reasons:

1. **IP + SNI correlation filtering.** The system knows all legitimate Google IP addresses. Your VPN server is hosted by a foreign provider (Hetzner, DigitalOcean). The censor sees: the packet is marked as `dl.google.com` but is going to a suspicious IP of a third-party datacenter. Instant session reset.

2. **Traffic volume limits.** A regular website request is a short exchange. A full VPN tunnel is a continuous stream of heavy packets. As soon as more than 15–20 KB is transferred within a single session to "Google," the connection is terminated.

**Conclusion:** a standalone VLESS Reality targeting a foreign VPS is useless under whitelist conditions, no matter which domain it masquerades as.

---

### How This Is Bypassed: Three Schemes

#### 1. Double Tunnel ("Bridge" in Russia)

A chain of two servers is created:

- **Entry server (Bridge)** is located inside Russia in a major provider's datacenter (VK Cloud, Yandex Cloud). Since these clouds are on the whitelist, your smartphone can send data there without issues.
- **Exit server** is located abroad. The Russian bridge receives your encrypted traffic and forwards it to the foreign server, opening access to the entire internet.

#### 2. Masquerading as Allowed Protocols (Stealth Technologies)

TSPU filtering systems analyze packet structure. To fool them, modern protocols are used (VLESS + Reality, xHTTP, WebSocket). Your traffic looks to the ISP like a regular video call, VK Video streaming, or Yandex Disk activity — all legally allowed within the whitelist.

#### 3. Routing Through CDN

Traffic is routed through large CDN networks. If CDN IP addresses are on the whitelist (to ensure some important app works), the VPN client connects to a CDN node inside the country, which then acts as a proxy to the final destination abroad.

---

### The Cost: Privacy and Stability

The main vulnerability of this scheme is that the bridge **must** reside on a "whitelisted" IP address. In Russia, such addresses belong only to major tech giants (VK Cloud, Yandex Cloud, Selectel, Rostelecom). All of them unconditionally comply with Russian laws and cooperate with Roskomnadzor.

**What the Russian cloud logs:**
- Your real IP address (home internet or mobile provider).
- Exact connection time and traffic volume.
- Your foreign server's IP address.

**What they DON'T see:** the content of your traffic. It's encrypted twice: first by the VPN protocol (VLESS), then by HTTPS. The Russian bridge only sees a stream of encrypted bytes.

**Main risks:**
- **Account suspension.** If a single virtual server generates a massive stream of encrypted traffic to a foreign IP, the account on Yandex or VK Cloud will be suspended.
- **Identity linking.** Renting a server in Russia requires a passport, Gosuslugi account, or Russian bank card. The state will know exactly who rented the bridge.
- **Chain break.** Roskomnadzor sees that a Russian IP is communicating with a foreign one. That foreign IP is instantly added to the TSPU blacklist, and the chain breaks.

---

### Why This Is Not an Ideal Solution

1. **Constant cat-and-mouse game.** Roskomnadzor regularly closes loopholes: forbids cloud providers from leasing "whitelisted" IPs to third-party VPNs, and blocks suspicious requests to government clouds.

2. **Speed degradation.** The signal goes through an intermediate Russian server and undergoes heavy masking. Speed drops, latency increases.

3. **Mass ban risk.** If users are massively accessing Instagram or YouTube through a single "whitelisted" gateway, TSPU algorithms detect the anomaly and block the server.

---

### Summary

| | DPI (Blacklists) | Whitelists |
|---|---|---|
| How it works | Packet content analysis | Destination address verification |
| What is blocked | Specific sites and VPN protocols | Everything except allowed Russian sites |
| Effectiveness against VPN | Medium (bypassed by Reality) | Absolute (blocks any foreign VPN) |
| When applied | Everyday mode | Emergencies, counter-terrorism operations |

**Conclusion:** commercial VPNs advertising "whitelist mode" either use bridges in Russian clouds or exploit routing holes in CDN infrastructure. For the end user, this means: there is no privacy from the state in this scheme. The state knows you're using a VPN, knows your IP, and knows your server's IP. But it's a working compromise if your goal during a hard shutdown is simply to maintain connectivity to the outside world.

**Self-hosting:** a standalone VLESS Reality on a foreign VPS is useless under whitelists. A two-stage chain (Russia bridge + foreign server) is required. Technical setup details are beyond the scope of this book, but the concept is described above.
