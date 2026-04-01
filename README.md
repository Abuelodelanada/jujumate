# ⬢ JujuMate

[![CI](https://github.com/Abuelodelanada/jujumate/actions/workflows/ci.yaml/badge.svg)](https://github.com/Abuelodelanada/jujumate/actions/workflows/ci.yaml)
[![Coverage](https://codecov.io/gh/Abuelodelanada/jujumate/graph/badge.svg)](https://codecov.io/gh/Abuelodelanada/jujumate)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![uv](https://img.shields.io/badge/packaged%20with-uv-purple)](https://docs.astral.sh/uv)

> A terminal UI for [Juju](https://juju.is) — monitor all your infrastructure resources in a single interactive screen with real-time updates. Inspired by [K9s](https://k9scli.io/) and [KDash](https://github.com/kdash-rs/kdash).

[![asciicast](https://asciinema.org/a/2CEYUKKPbHc9Ch0R.svg)](https://asciinema.org/a/2CEYUKKPbHc9Ch0R)

---

## Features

- 🔄 **Auto-refresh** — status updates automatically every few seconds; logs stream live via WebSocket
- ☁️ **Full resource tree** — clouds, controllers, models, applications, units, machines
- 📊 **Status view** — apps, units, offers, integrations, SAAS and machines in one screen
- 🏥 **Health view** — shows only unhealthy models by default; toggle to see all with `f`
- 🔍 **Drill-down navigation** — select a controller → filter models; select a model → see its full status
- 🔎 **Inline filtering** — press `/` in Status or Logs to search with live highlight
- 🔗 **Peer relation toggle** — press `p` to show/hide peer relations in the Integrations panel
- 🖥️ **Units-per-machine toggle** — press `u` to show units (and their subordinates) nested under each machine
- 🗂️ **Collapsible panels** — press `x` to collapse/expand any Status panel individually; focused panel highlighted in theme colour
- 👑 **Leader indicators** — unit leaders marked with `*` (green) following `juju status` convention
- 🔗 **Relation lifecycle** — Integrations panel shows live relation status; relations being torn down display as `removing`
- 📋 **Copy to clipboard** — press `y` in Status or Relation Data to copy the full content
- 🔐 **Secrets browser** — list and inspect Juju secrets per model (`Shift+S`)
- 📦 **Offers browser** — browse all cross-model offers in a controller, with endpoint details and live consumer tracking across controllers (`Shift+O`)
- 📋 **Relation databag inspector** — examine raw relation data for any relation (`Enter` on a relation)
- ⚙️ **App config viewer** — inspect application configuration (`Enter` on an app)
- 🖥️ **Machine detail modal** — press `Enter` on any machine to see hardware specs, status timestamps and network interfaces
- 🎨 **Themeable** — five built-in themes; fully customisable via YAML
- ⚙️ **Settings modal** — change theme, refresh interval, default controller and log level at runtime (`Shift+C`)
- 🪟 **Terminal transparency** — respects your terminal background (no forced black background)
- ⌨️ **K9s-style help overlay** — press `?` to see all keybindings at any time (full-screen)

---

## Installation

**Recommended — install as a tool with uv:**

```bash
uv tool install jujumate
```

**Or with pipx:**

```bash
pipx install jujumate
```

JujuMate reads your existing Juju configuration from `~/.local/share/juju/` automatically — no extra setup needed if `juju` is already working.

---

## Quick Start

```bash
jujumate
```

On first launch JujuMate connects to your current Juju controller and auto-selects your current model. Use the keyboard shortcuts below to navigate.

---

## Keyboard Shortcuts

### Global

| Key | Action |
|-----|--------|
| `c` | Go to Clouds tab |
| `m` | Go to Models tab |
| `s` | Go to Status tab |
| `h` | Go to Health tab |
| `r` | Force refresh |
| `Esc` | Clear cloud/controller drill-down filter |
| `?` | Toggle help overlay |
| `q` | Quit |

### Navigation

| Key | Action |
|-----|--------|
| `↑` / `↓` | Move cursor up/down |
| `Enter` | Drill-down / open detail |

### Status tab

| Key | Action |
|-----|--------|
| `/` | Filter by app name, charm, channel or message (with live highlight) |
| `Esc` | Clear filter |
| `p` | Toggle peer relations in the Integrations panel |
| `u` | Toggle units (and subordinates) nested under each machine |
| `x` | Collapse/expand the current panel |
| `y` | Copy full status to clipboard (includes cloud, controller, model and Juju version) |
| `Enter` on app | Open App Config viewer |
| `Enter` on offer | Open Offer detail |
| `Enter` on relation | Open Relation Data inspector |
| `Enter` on machine | Open Machine detail modal (hardware, status, network) |

### Health tab

| Key | Action |
|-----|--------|
| `f` | Toggle between unhealthy-only (default) and all models |

### Modals

| Key | Action |
|-----|--------|
| `Shift+S` | Open Secrets browser for the current model |
| `Shift+O` | Open Offers browser for the current controller |
| `Shift+L` | Open live Log viewer for the current model |
| `Shift+C` | Open Settings modal (appearance, behaviour, diagnostics) |
| `Enter` | Open detail view |
| `y` | Copy value to clipboard (Relation Data / Secrets) |
| `Esc` | Close modal |

---

## Views

### Status
The main view. Displays a full `juju status`-style breakdown of the selected model:
- **Applications** — name, charm, channel, revision, units, status and workload message
- **Units** — workload/agent status, machine or pod, address, ports; subordinates shown nested under their principal; leader units are marked with `*`
- **Machines** — id, state, address, instance, base, AZ *(IaaS models only)*; press `u` to expand units and their subordinates inline; press `Enter` on a machine to open its detail modal

Press `Enter` on a machine to see:
- **Hardware** — architecture, CPU cores, memory, root disk size, virtualisation type
- **Status** — agent and instance status with relative timestamps (e.g. *2h ago*)
- **Network interfaces** — name, IP address, MAC address and Juju space for each NIC
- **SAAS** — consumed remote offers and their status
- **Offers** — cross-model offers with active/total connection counts
- **Integrations** — regular and cross-model relations with live status column (peer relations hidden by default; press `p` to toggle); relations being removed show as `removing`

Each panel can be collapsed individually with `x` while it has focus, and expanded again with `x`. The focused panel is highlighted with a distinct border colour (violet in Monokai and Ubuntu themes).

### Health
Shows a summary of all models across all controllers, highlighting those with errors or blocked units. Unhealthy models are shown by default; press `f` to toggle between unhealthy-only and all models.

### Offers browser (`Shift+O`)
Lists all offers across every model in the current controller. Select an offer to see:
- Model, URL, application, charm, description and access level
- Endpoint details (name, interface, role)
- Live consumer list — scans all known controllers to find which models and applications are consuming the offer

### Secrets browser (`Shift+S`)
Lists all secrets visible in the current model. Select a secret to see its metadata (owner, revision, rotation policy, timestamps).

### Log viewer (`Shift+L`)
Streams live log entries from the current model. Use `/` to filter by text.

### Relation Data inspector
Press `Enter` on any relation in the Status tab to open a databag viewer showing the application-level and unit-level relation data for both sides of the relation. Press `y` to copy the full content to clipboard.

### App Config viewer
Press `Enter` on any application in the Status tab to inspect its current configuration values.

### Machine detail modal
Press `Enter` on any machine row in the Machines panel to open a modal showing:
- Instance ID, address, base OS, availability zone, controller and model
- **Hardware** — architecture, CPU cores, memory, root disk size and virtualisation type (parsed from Juju's hardware string)
- **Status** — agent and instance status with relative timestamps (e.g. *started 2h ago*)
- **Network interfaces** — name, IP address, MAC address and Juju space for each NIC

Section titles adapt to the active theme's accent colour. Press `Esc` to close.

---

## Configuration

JujuMate is configured via `~/.config/jujumate/config.yaml`. All fields are optional.

```yaml
# ~/.config/jujumate/config.yaml

theme: ubuntu               # Theme name (default: ubuntu)
refresh_interval: 5         # Seconds between auto-refresh (default: 5)
offers_cache_ttl: 300       # Seconds to cache the offers list (default: 300)
default_controller: prod    # Controller to use (default: current Juju controller)
log_file: ~/.local/state/jujumate/jujumate.log
log_level: INFO             # DEBUG | INFO | WARNING | ERROR | CRITICAL
```

Most settings can also be changed at runtime — press `Shift+C` to open the **Settings modal**, which lets you change the theme (with live preview), refresh interval, default controller and log level without editing the file manually. Changes are saved immediately.

> **`offers_cache_ttl`** is a config-file-only setting (not exposed in the Settings modal). It controls how long the Offers list is cached between modal opens. Press `r` inside the Offers modal to force an immediate refresh.

---

## Themes

JujuMate ships with five built-in themes: **`ubuntu`** (default), **`dark`**, **`monokai`**, **`solarized-dark`** and **`spacemacs`**.

Press `Shift+C` to open the Settings modal, then select a theme in the **Appearance** section to preview it live before it's applied.

To create a custom theme, add a YAML file to `~/.config/jujumate/themes/`:

```yaml
# ~/.config/jujumate/themes/mytheme.yaml
name: mytheme
primary: "#FF6600"
secondary: "#003366"
background: "#1a1a2e"
surface: "#16213e"
dark: true
```

Then set it in your config:

```yaml
theme: mytheme
```

Available fields: `primary`, `secondary`, `accent`, `background`, `surface`, `panel`, `warning`, `error`, `success`, `foreground`, `dark`.

User themes override built-in themes with the same name.

---

## Development

**Requirements:** Python 3.10+, [uv](https://docs.astral.sh/uv)

```bash
git clone https://github.com/Abuelodelanada/jujumate.git
cd jujumate
uv sync
```

**Run from source:**

```bash
uv run jujumate
```

**Run checks (lint + typecheck + tests):**

```bash
uv run nox
```

**Individual sessions:**

```bash
uv run nox -s tests       # Run tests with coverage
uv run nox -s lint        # Ruff lint + format check
uv run nox -s typecheck   # Pyright static analysis
uv run ruff format src tests  # Auto-format code
```

---

## License

[GNU General Public License v3.0](LICENSE)
