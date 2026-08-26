## Hiddify Client Settings

In Hiddify Manager, client ports are configured automatically when you enable the necessary protocols. In the client (Hiddify App), these ports need to be linked to local operation through the Inbound settings.

Briefly about ports: these are local ports on your device through which other programs (Telegram, browser) route their traffic into Hiddify.

---

### Main Operating Modes

Hiddify client has three main modes:

- **TUN (VPN)** — intercepts all system traffic at the OS level through a virtual network interface. Everything works automatically, no app configuration needed. On Android/iOS — the standard choice.
- **System Proxy** — enables system-wide proxy settings in the OS. Apps that respect these settings (browsers, some messengers) go through Hiddify automatically. Those that ignore system settings — don't.
- **Proxy (Inbounds)** — starts a local proxy server (HTTP/SOCKS5) on a specific port. You manually configure this proxy in the apps you need.

**What to choose:**
- Android/iOS — **TUN**. Just works.
- Desktop (Windows/macOS) — usually **System Proxy** if apps use it correctly.
- Linux — **System Proxy** or **Proxy**, but not TUN unless necessary.
- If you need to route only Telegram or browser through the proxy and leave everything else untouched — **Proxy**.

---

### Port Configuration (Inbounds)

In Hiddify settings (Settings → Core Settings / Inbounds) you'll see:

- **Mixed Port** (usually 2334 or 10808) — accepts both HTTP and SOCKS5. Universal port.
- **Socks Port** (may be separate if Mixed is disabled) — SOCKS5 only.

For manual configuration in apps use:
- Host: `127.0.0.1`
- Port: the number from Mixed Port (e.g., `2334`)

The other ports (Transparent Proxy, Redirect, Direct) are internal — used by the kernel for its own purposes. In Proxy mode they're not used, you can ignore them.

> **Important:** the port can be changed — always check the actual value in the Inbounds section.

---

### HTTP vs SOCKS5

| | HTTP Proxy | SOCKS5 |
|---|---|---|
| Purpose | Web traffic (browsers) | Universal — any traffic |
| Protocols | TCP | TCP + UDP |
| When to use | Browsers, extensions | Messengers, calls, games, torrents |

In the context of Hiddify: if configuring manually, choose SOCKS5 for Telegram. For browser via extension — HTTP or SOCKS5 (if supported).

---

### App Configuration

#### Telegram (SOCKS5 recommended)

1. Open Telegram → Settings → Advanced → Connection Type (in some versions: Data and Storage → Proxy Settings).
2. Tap **Add Proxy** → select **SOCKS5**.
3. Enter:
   - Host: `127.0.0.1`
   - Port: `2334` (or your actual port)
   - Username and Password: leave empty
4. Save and enable the proxy.

#### Browser

- If **System Proxy** is enabled — the browser already goes through Hiddify, nothing to configure.
- If System Proxy is disabled — use an extension (Proxy SwitchyOmega, FastProxy):
  1. Install the extension.
  2. Create a new profile.
  3. Select HTTP (or SOCKS5 if supported).
  4. Server: `127.0.0.1`, port: `2334`.

---

### TUN Mode (VPN)

In this mode, Hiddify creates a virtual network adapter in the OS. All internet traffic is automatically routed through the VPN at the system level.

**How to enable:**

1. Reset manual settings in apps:
   - Telegram: revert to "Use system settings" (or "Default").
   - Browser: disable proxy extensions or switch them to "System Proxy" mode.
2. In Hiddify: Settings → Core Settings → Service Mode → select **TUN**.
3. Click **Connect**.

**Important notes:**

- On Windows/Linux, administrator privileges may be required to create the adapter.
- On Android/iOS, TUN works through the built-in VPN interface — root is not required. Confirm the permission on first activation.
- **Linux:** running the Hiddify GUI through `sudo` is strongly discouraged — it's unsafe. TUN on Linux requires privileges, but they can be granted separately without running the entire application as root.

**How ports work in TUN mode:**

- **Mixed Port** — continues to work. Can be used to manually route individual apps that don't recognize TUN.
- **Transparent Proxy / Redirect / Direct** — internal, used by the kernel. Don't touch them manually.

With TUN enabled, you usually don't need to manually configure proxies in Telegram or browser — they'll go through Hiddify automatically.

---

### Mode Comparison

| | TUN | System Proxy | Proxy (Inbounds) |
|---|---|---|---|
| What it does | Intercepts all traffic at OS level | Enables system proxy | Starts a local proxy server |
| For whom | All apps automatically | Apps that respect system settings | Manual configuration of specific apps |
| Requires privileges | Yes (adapter creation) | No | No |
| When to use | You want everything to work without config | Apps work correctly with system proxy | You need selective proxying (Telegram only, browser only) |
