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
- 🔍 **Drill-down navigation** — select a controller → filter models; select a model → see its full status
- 🔎 **Inline filtering** — press `/` in Status to search across apps, charms, channels and messages
- 🔐 **Secrets browser** — list and inspect Juju secrets per model (`Shift+S`)
- 📦 **Offers browser** — browse all cross-model offers in a controller, with endpoint details and live consumer tracking across controllers (`Shift+O`)
- 📋 **Relation databag inspector** — examine raw relation data for any relation (`Enter` on a relation)
- ⚙️ **App config viewer** — inspect application configuration (`Enter` on an app)
- 🎨 **Themeable** — built-in `ubuntu` and `dark` themes; fully customisable via YAML
- 🪟 **Terminal transparency** — respects your terminal background (no forced black background)
- ⌨️ **K9s-style help overlay** — press `?` to see all keybindings at any time

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
| `C` | Go to Controllers tab |
| `m` | Go to Models tab |
| `s` | Go to Status tab |
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
| `/` | Filter by app name, charm, channel or message |
| `Esc` | Clear filter |
| `Enter` on app | Open App Config viewer |
| `Enter` on offer | Open Offer detail |
| `Enter` on relation | Open Relation Data inspector |

### Modals

| Key | Action |
|-----|--------|
| `Shift+S` | Open Secrets browser for the current model |
| `Shift+O` | Open Offers browser for the current controller |
| `Shift+L` | Open live Log viewer for the current model |
| `T` | Open theme switcher |
| `Enter` | Open detail view |
| `y` | Copy value to clipboard (Relation Data / Secrets) |
| `Esc` | Close modal |

---

## Views

### Status
The main view. Displays a full `juju status`-style breakdown of the selected model:
- **Applications** — name, charm, channel, revision, units, status and workload message
- **Units** — workload/agent status, machine or pod, address, ports
- **Machines** — id, state, address, instance, base, AZ *(IaaS models only)*
- **SAAS** — consumed remote offers and their status
- **Offers** — cross-model offers with active/total connection counts
- **Integrations** — all relations (peer, regular and cross-model)

### Offers browser (`Shift+O`)
Lists all offers across every model in the current controller. Select an offer to see:
- Model, URL, application, charm, description and access level
- Endpoint details (name, interface, role)
- Live consumer list — scans all known controllers to find which models and applications are consuming the offer

### Secrets browser (`Shift+S`)
Lists all secrets visible in the current model. Select a secret to see its metadata (owner, revision, rotation policy, timestamps).

### Relation Data inspector
Press `Enter` on any relation in the Status tab to open a databag viewer showing the application-level and unit-level relation data for both sides of the relation.

### App Config viewer
Press `Enter` on any application in the Status tab to inspect its current configuration values.

---

## Configuration

JujuMate is configured via `~/.config/jujumate/config.yaml`. All fields are optional.

```yaml
# ~/.config/jujumate/config.yaml

theme: ubuntu               # Theme name (default: ubuntu)
refresh_interval: 5         # Seconds between auto-refresh (default: 5)
default_controller: prod    # Controller to use (default: current Juju controller)
log_file: ~/.local/state/jujumate/jujumate.log
log_level: INFO             # DEBUG | INFO | WARNING | ERROR | CRITICAL
```

---

## Themes

JujuMate ships with five built-in themes: **`ubuntu`** (default), **`dark`**, **`monokai`**, **`solarized-dark`** and **`spacemacs`**.

Press `T` at any time to open the live theme switcher and preview themes before applying them.

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
