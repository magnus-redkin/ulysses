# Jungle Book

A technical guide to survival and bypassing censorship in today's digital jungles.

This documentation covers not only Hiddify-Manager but also the broader ecosystem of censorship circumvention. It brings together knowledge about protocols, architecture, threats, and tools that help you stay afloat under heavy censorship.


## Laws of the Digital Jungle

1. **The Law of Invisibility.** Any circumvention method works only as long as its traffic is indistinguishable from legitimate user behavior.

2. **The Law of Environment.** The local censor sees your traffic on the backbone. Corporate spies control the very environment you operate in — your device. Protection must be comprehensive.


## The Ulysses Ecosystem

At the core of this book is an ecosystem of circumvention tools built around Hiddify-Manager.

**Ulysses** — a wrapper around Hiddify-Manager. Admin panel, email, Telegram bot, and other interfaces for managing the service. Unlike typical VPNs, the HFM IP address is hidden from users — they only work through gateways.

Ulysses can use any protocol supported by Hiddify-Manager, but currently Reality + xHTTP are active.

**Gateways (Entry Gates)** — any number of entry nodes in different locations. These are what users actually connect to. Gateways get blocked by Roskomnadzor and other censors — it's an inevitable process.

**Gryphon** (in development) — a gateway state analyzer and manager. If a gateway is blocked, Gryphon automatically replaces its IP with another from a pool of backup addresses. This is an open alternative to Cloudflare-style concealment — no CDN spyware, just address replacement, with open source code and a free license.

> **Gryphon status:** actively in development. This version of the book covers the concept only. Architecture and setup details will appear in future editions.
