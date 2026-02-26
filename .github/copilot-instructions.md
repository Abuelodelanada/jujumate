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
├── jujumate/
│   ├── __main__.py          # Entry point: python -m jujumate
│   ├── app.py               # Main Textual App
│   ├── config.py            # Reads ~/.local/share/juju/ (controllers, accounts)
│   ├── client/
│   │   ├── juju_client.py   # python-libjuju wrapper (connect, get_status, clouds)
│   │   └── watcher.py       # Bridge: libjuju AllWatcher → Textual messages
│   ├── screens/
│   │   └── main_screen.py   # Layout: header + TabbedContent + footer
│   ├── widgets/
│   │   ├── resource_table.py  # Generic reusable DataTable
│   │   ├── clouds_view.py
│   │   ├── controllers_view.py
│   │   ├── models_view.py
│   │   ├── apps_view.py
│   │   └── units_view.py
│   └── models/
│       └── entities.py      # Dataclasses: CloudInfo, ControllerInfo, ModelInfo, AppInfo, UnitInfo
└── tests/
```

## Architecture

### Real-time data flow

```
Juju Controller
      │  WebSocket (RPC)
      ▼
python-libjuju AllWatcher
      │  asyncio callback
      ▼
Textual post_message()
      ▼
Widget.refresh() → updated screen
```

Textual and python-libjuju share the **same asyncio event loop** — no extra threads are needed or should be introduced.

### Authentication

python-libjuju automatically reads `~/.local/share/juju/` — the same config used by the Juju CLI. No additional configuration is needed if the user already has `juju` set up.

## UI conventions

### Keybindings

| Key | Action |
|-----|--------|
| `c` | Clouds tab |
| `C` | Controllers tab |
| `m` | Models tab |
| `a` | Applications tab |
| `u` | Units tab |
| `↑↓` | Navigate table rows |
| `Enter` | Drill-down (e.g. Model → its Apps) |
| `/` | Inline filter (K9s-style) |
| `r` | Force refresh |
| `q` | Quit |

### Table columns per view

| View | Columns |
|------|---------|
| Clouds | Name, Type, Regions, Credentials |
| Controllers | Name, Cloud, Region, Juju Version, Models count |
| Models | Name, Controller, Cloud/Region, Status, Machines, Apps |
| Applications | Name, Model, Charm, Channel, Rev, Units, Status, Message |
| Units | Name, App, Machine/Pod, Workload Status, Agent Status, Address |

### Status indicators

Use `●` colored dots for status: green = active, yellow = waiting/maintenance, red = error/blocked.

## Code conventions

- **No in-function imports**: All imports must be at the top of the file. Never place `import` or `from ... import` statements inside functions, methods, or test bodies.
- **Line length**: 100 characters max (configured in ruff).
- **Type hints**: Required on all public functions and methods.

## Distribution target

- **PyPI** (MVP): `pipx install jujumate` / `uv tool install jujumate`
- **Snap Store** (post-v1.0): natural fit since Juju itself is a snap
