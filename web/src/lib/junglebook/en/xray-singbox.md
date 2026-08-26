# Comparison of Proxy Cores: Xray vs Sing-box

Hiddify-Manager integrates two cores simultaneously: Xray-core and Sing-box. Understanding the differences between them helps with protocol selection and load optimization.

Xray is an evolution of V2Ray's classic ideas. Sing-box was designed from scratch as a new generation.

---

## Architecture and Performance

Both cores are written in Go, but their internal structure and resource approach differ.

**Xray-core**
- Modular, historically heavy V2Ray architecture.
- Extensive backward compatibility and flexibility.
- Consumes more RAM under high concurrent connection loads.

Ideal for classic servers with legacy, battle-tested configurations.

**Sing-box**
- Designed for maximum performance and minimal memory consumption.
- Built from the ground up with mobile devices and low-end VPS in mind.
- Processes packets faster, spends less CPU on encryption.

---

## Protocol and Technology Support

**Xray-core**
- The birthplace of Reality technology and XTLS extensions.
- The gold standard for VLESS-Reality over TCP and WebSockets.
- Best choice for stable masking through traditional protocol stacks.

**Sing-box**
- Leader in next-generation UDP protocols.
- Native implementation of Hysteria2 and TUIC (v5).
- Actively promotes HTTPUpgrade and XHTTP, which are replacing older WebSockets.
- Built-in WireGuard support at the kernel level.

---

## Routing and DNS Processing

**Xray-core**
- Classic routing scheme.
- Requires sniffing to extract domain names from TLS handshakes for traffic analysis.
- GeoIP/GeoSite databases in .dat format — larger footprint, slower to load.

**Sing-box**
- New declarative routing system.
- Rule databases in .srs format — binary, optimized for instant RAM lookups.
- DNS engine works as an independent resolver with flexible query branching (parallel DoH requests).

---

## Integration into Hiddify

Hiddify-Manager doesn't force you to choose one core — the panel leverages the strengths of both:

**On the server:**
- Both cores run in parallel.
- VLESS-Reality-TCP is handled by Xray.
- Hysteria2 and TUIC go to Sing-box.

**On the client (Hiddify App):**
- Clients for Windows, Android, iOS, macOS are built exclusively on Sing-box.
- This provides smooth operation, battery savings, and fast processing of configs with thousands of rules.

---

## Final Comparison Table

| Parameter | Xray-core | Sing-box |
|:---------|:----------|:---------|
| Memory consumption | Medium / High | Extremely low |
| UDP performance | Standard | Maximum (QUIC) |
| Primary protocols | VLESS, Trojan, Shadowsocks | Hysteria2, TUIC, XHTTP |
| Reality | Original implementation | Ported implementation |
| Geo-database format | .dat (heavy) | .srs (light, fast) |
| Mobile optimization | Adequate | Ideal |

---

**Summary:** Xray is the choice for stable server configurations with classic protocols. Sing-box is the future — lightweight, fast, ideal for mobile devices and new UDP protocols. Hiddify uses both where they excel.
