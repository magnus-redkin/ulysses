# Why Ulysses provides two links: Global and Russia

## In short

We provide two links not because it's easier for us, but because **Hiddify — our primary recommended client — fundamentally does not allow the provider VPN (Ulysses for example) to control routing on the user's device**. This is a deliberate choice made by Hiddify's developers in favor of security.

## Why this is so

Hiddify builds its architecture on the principle of **"Zero Trust"** toward all external sources — including our subscription. Routing rules (`route.rules`) that we could embed in the subscription are **ignored** by the client.

The reasons behind this decision are sound:

- **Protection against server compromise.** If Hiddify blindly executed rules from the subscription, any attacker who gained access to our backend could redirect all users' traffic to their own server — to intercept passwords and banking data.
- **Prevention of rule "poisoning."** Even with a secure server, the subscription link itself can be intercepted. In unencrypted form, the token and node parameters could be compromised.
- **The "client is the owner" philosophy.** In Hiddify's view, control over routing should remain with the user, not the provider.

**This is not a bug. It is a philosophy.**

We could switch to another client where `route.rules` do work — Happ, sing-box, Nekoray, Karing. But:

- **Happ** — closed source. Offering it while talking about privacy is a contradiction.
- **Karing, sing-box CLI** — the interface is overloaded, suitable only for geeks. Not appropriate for a commercial VPN.
- **Hiddify** — the best balance of simplicity and openness. That is why we work with it.

## What this means in practice

There are two fundamentally different ways to route traffic:

**Automatic routing** (`route.rules`) — the rules say: "domain `.ru` → go through the RU node, everything else → through EU." The user does nothing; traffic splits by itself. **This does not work in Hiddify.**

**Manual server selection** — the user switches the node themselves. While set to EU — all traffic goes through EU (YouTube, Telegram work, Gosuslugi does not). Switch to RU — all traffic goes through RU (Gosuslugi works, YouTube and Telegram do not). **This works in Hiddify, but gives "all or nothing."**

Getting "Gosuslugi through RU + YouTube through EU" simultaneously in Hiddify is not possible.

## Then why two subscriptions instead of one

Technically, we could make **one subscription** with all nodes — NL, BG, RU. The user would select the needed one manually.

But this is bad for two reasons:

**1. The auto-selector chooses the wrong node.** By default, Hiddify uses `lowest` — automatic selection by minimum ping. If the auto-selector picks EU — Gosuslugi will not open. If it picks RU — Telegram and everything else will break. The user ends up with a VPN that doesn't work "out of the box."

**2. The server list turns into a mess.** One subscription would show `VLESS Reality [NL]`, `VLESS Reality [BG]`, `VLESS Reality [RU]`, `Hysteria2 [NL]`, `Hysteria2 [BG]`... The user has no idea what to choose.

**Two subscriptions solve both problems:**

| Subscription | For whom | What is inside |
|---|---|---|
| **🌍 Global** | Users in Russia, expats for everyday use | EU nodes (NL, BG) with automatic selection |
| **🇷🇺 Russia** | Expats for Russian services | RU node |

**Global** — a user in Russia taps Connect, kicks back on the couch, and watches YouTube.
**Russia** — an expat taps Connect, opens Gosuslugi, Sber, and watches Russian TV.

## If the main profile doesn't work: Compat

In rare cases, the **Global** subscription may not work. There are two reasons:

- **An outdated client** that does not support the `xhttp` transport. In this case, the client may fail to load the entire config.
- **Happ on iOS**: the Reality + XHTTP combination sometimes fails to pass data, even though the connection is established.

For these cases, we've created **Compat** — the same Global subscription, but **without xhttp**. It contains only VLESS Reality, VLESS Reality grpc, and Hysteria2, which every client understands.

**When to use Compat:**

- If you are on an **iPhone/iPad** and Happ does not pass traffic through Global.
- If your client is **older than a year** and does not support xhttp.
- If you simply want **maximum compatibility** and don't need xhttp.

You can find the Compat link in your **Personal Account**, in the "Compatibility" section. We don't show it in the bot to avoid confusing users: 95% work fine with Global and Russia, and Compat is a fallback for special cases.

## Bottom line

- **Automatic traffic splitting does not exist in Hiddify** — this is an architectural limitation of the client, not a shortcoming on our side.
- **Two links are honest.** The user understands what they are choosing: "regular internet" or "Russian IP."
- **Switching takes 2 taps** in Hiddify. It always works. No inexplicable situations like "Gosuslugi is blocked but YouTube works."

This is the maximum Hiddify offers. And it is better than a single link that only half-works.

## A curious side effect for expats

Expats don't need the Global subscription; Telegram and YouTube work for them anyway. And residents of the Russian Federation don't need the Russia version. That’s true, but...

When Global is enabled, expats may suddenly find that sites and services which **"didn't work without a VPN"** start working. For example, `bolshoi.ru`, `tvigle.ru`, some banking services.

The reason is not RKN blocking, nor that the site is "blocked for all foreigners." The reasons usually relate to the anti-fraud systems of specific resources, and they are:

- **The site blocks a specific country** — e.g., Germany — but not the Netherlands or Bulgaria.
- **The site blocks a specific ISP** — e.g., a German one — but not our hosting provider.
- **The site applies anti-fraud filters** — by IP, geolocation, address reputation. And the rules are different for every site.

Through Global (NL/BG), you simply look like a resident of a different country with a different ISP. Sometimes that is enough for the filter to let you through.
