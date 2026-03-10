# ⬢ JujuMate

**A terminal UI for [Juju](https://juju.is)** — monitor all your infrastructure resources in a single interactive screen with real-time updates. Inspired by [K9s](https://k9scli.io/) and [KDash](https://github.com/kdash-rs/kdash).

[Get Started](installation.md){ .md-button .md-button--primary }
[View on GitHub](https://github.com/Abuelodelanada/jujumate){ .md-button }

---

![JujuMate screenshot](https://github.com/user-attachments/assets/8382e7a7-bb60-4fab-93bc-cade54cbb025)

---

## Demo

<link rel="stylesheet" type="text/css" href="https://cdn.jsdelivr.net/npm/asciinema-player@3/dist/bundle/player.css" />
<div id="demo" class="asciinema-player-container"></div>
<script src="https://cdn.jsdelivr.net/npm/asciinema-player@3/dist/bundle/player.min.js"></script>
<script>
  AsciinemaPlayer.create(
    'assets/demo.cast',
    document.getElementById('demo'),
    { cols: 220, rows: 50, autoPlay: false, loop: true, theme: 'monokai' }
  );
</script>

---

## Features

- 🔄 **Auto-refresh** — status updates automatically every few seconds; logs stream live via WebSocket
- ☁️ **Full resource tree** — clouds, controllers, models, applications, units, machines
- 📊 **Status view** — apps, units, offers, integrations, SAAS and machines in one screen
- 🔍 **Drill-down navigation** — select a controller → filter models; select a model → see its full status
- 🔎 **Inline filtering** — press `/` in Status to search across apps, charms, channels and messages
- 🔐 **Secrets browser** — list and inspect Juju secrets per model (`Shift+S`)
- 📦 **Offers browser** — browse all cross-model offers with endpoint details and live consumer tracking (`Shift+O`)
- 📋 **Relation databag inspector** — examine raw relation data for any relation (`Enter` on a relation)
- ⚙️ **App config viewer** — inspect application configuration (`Enter` on an app)
- 📜 **Live log viewer** — stream model logs in real time, with filtering and local timezone display (`Shift+L`)
- 🎨 **Themeable** — five built-in themes; fully customisable via YAML
- 🪟 **Terminal transparency** — respects your terminal background
- ⌨️ **K9s-style help overlay** — press `?` to see all keybindings at any time

---

## Quick Install

=== "uv (recommended)"

    ```bash
    uv tool install jujumate
    ```

=== "pipx"

    ```bash
    pipx install jujumate
    ```

JujuMate reads your existing Juju configuration from `~/.local/share/juju/` automatically — no extra setup needed if `juju` is already working.

```bash
jujumate
```
