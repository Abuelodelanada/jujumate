# JujuMate — Copilot Instructions

JujuMate is a TUI (Terminal User Interface) for [Juju](https://juju.is), Canonical's infrastructure orchestration engine. It provides a single interactive screen showing all Juju resources (clouds, controllers, models, applications, units) with real-time updates — inspired by K9s and KDash.

## Tech stack

| Tool | Purpose |
|------|---------|
| Python 3.10+ | Language |
| [Textual](https://textual.textualize.io) | TUI framework (asyncio-native, CSS layout, DataTable/Tabs built-in) |
| [python-libjuju](https://github.com/juju/python-libjuju) | Official Juju SDK (`pip install juju`); asyncio-first; supports AllWatcher for real-time updates |
| [uv](https://docs.astral.sh/uv) | Package manager (replaces pip + venv + build) |
| pytest | Unit testing |

## Commands

```bash
uv run nox                # Run all checks (lint + typecheck + tests)
uv run nox -s tests       # Run all tests
uv run nox -s lint        # Ruff lint + format check
uv run nox -s typecheck   # Pyright static analysis
uv run nox -s tests -- tests/path/to/test_file.py::test_name  # Run a single test
uv run ruff format src tests  # Auto-format code
```

## Project structure

```
jujumate/
├── pyproject.toml
├── src/jujumate/
│   ├── __main__.py            # Entry point: python -m jujumate
│   ├── app.py                 # Main Textual App (CSS, theme, transparency)
│   ├── config.py              # Reads ~/.local/share/juju/ (controllers, accounts)
│   ├── settings.py            # User config from ~/.config/jujumate/config.yaml
│   ├── log.py                 # Rotating file logging setup
│   ├── theme_loader.py        # Loads YAML themes (builtin + user overrides)
│   ├── client/
│   │   ├── juju_client.py     # python-libjuju wrapper (connect, get_status, clouds)
│   │   └── watcher.py         # Poller: periodic data fetch → Textual messages
│   ├── screens/
│   │   ├── main_screen.py     # Layout: header + TabbedContent (no footer)
│   │   └── help_screen.py     # Modal overlay with keyboard shortcuts (? key)
│   ├── widgets/
│   │   ├── resource_table.py  # Generic reusable DataTable base
│   │   ├── jujumate_header.py # Custom header: context, counts, connection status
│   │   ├── clouds_view.py
│   │   ├── controllers_view.py
│   │   ├── models_view.py
│   │   ├── apps_view.py
│   │   ├── units_view.py
│   │   └── status_view.py     # Combined view: apps + units + offers + relations
│   ├── models/
│   │   └── entities.py        # Dataclasses: CloudInfo, ControllerInfo, ModelInfo,
│   │                          #   AppInfo, UnitInfo, OfferInfo, RelationInfo
│   └── themes/
│       ├── dark.yaml          # Default dark theme
│       └── ubuntu.yaml        # Ubuntu brand theme
└── tests/
```

## Architecture

### Real-time data flow

```
Juju Controller
      │  WebSocket (RPC)
      ▼
python-libjuju (JujuClient)
      │  asyncio (JujuPoller periodic poll)
      ▼
Textual post_message()
      ▼
MainScreen handlers → Widget.update() → screen refreshed
```

Textual and python-libjuju share the **same asyncio event loop** — no extra threads are needed or should be introduced.

### Authentication

python-libjuju automatically reads `~/.local/share/juju/` — the same config used by the Juju CLI. No additional configuration is needed if the user already has `juju` set up.

### Terminal transparency

The app uses `background: ansi_default` CSS and excludes Textual's `ANSIToTruecolor` line filter (via `get_line_filters()` override) so backgrounds emit `\x1b[49m` (terminal default) instead of explicit RGB. This preserves terminal transparency settings.

## UI conventions

### Keybindings

| Key | Action |
|-----|--------|
| `c` | Clouds tab |
| `C` | Controllers tab |
| `m` | Models tab |
| `s` | Status tab |
| `a` | Apps tab |
| `u` | Units tab |
| `↑↓` | Navigate table rows |
| `Enter` | Drill-down (e.g. Model → its Apps) |
| `Esc` | Clear drill-down filter |
| `r` | Force refresh |
| `?` | Help overlay (shows all shortcuts) |
| `q` | Quit |

No persistent footer — shortcuts are shown on demand via `?` (K9s-style modal overlay).

### Table columns per view

| View | Columns |
|------|---------|
| Clouds | Name, Type, Regions, Credentials |
| Controllers | Name, Cloud, Region, Juju Version, Models |
| Models | Name, Controller, Cloud/Region, Status, Machines, Apps |
| Apps | Name, Model, Charm, Channel, Rev, Units, Status, Message |
| Units | Name, App, Machine/Pod, Workload, Agent, Address |
| Status > Apps | Name, Version, Status, Scale, Charm, Channel, Rev, Address, Exposed, Message |
| Status > Units (K8s) | Unit, Workload, Agent, Address, Ports, Message |
| Status > Units (IaaS) | Unit, Workload, Agent, Machine, Public Address, Ports, Message |
| Status > Offers | Offer, Application, Charm, Rev, Connected, Endpoint, Interface, Role |
| Status > Relations | Provider, Requirer, Interface, Type |

### Status indicators

Use `●` colored dots for status: green = active, yellow = waiting/maintenance, red = error/blocked.

## Code conventions

- **No in-function imports**: All imports must be at the top of the file. Never place `import` or `from ... import` statements inside functions, methods, or test bodies.
- **Line length**: 100 characters max (configured in ruff).
- **Type hints**: Required on all public functions and methods.

## Distribution target

- **PyPI** (MVP): `pipx install jujumate` / `uv tool install jujumate`
- **Snap Store** (post-v1.0): natural fit since Juju itself is a snap
