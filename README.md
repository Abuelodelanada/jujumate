# JujuMate

A terminal UI for [Juju](https://juju.is) — monitor all your infrastructure resources in a single interactive screen with real-time updates.

Inspired by [K9s](https://k9scli.io/) and [KDash](https://github.com/kdash-rs/kdash).

```
╭─ ⬢ JujuMate ──────────────────╮  cloud: aws  ›  controller: prod  ›  model: cos
│ Juju infrastructure TUI        │  ────────────────────────────────────────────────
│ ⣾ Live · 12:34:56              │  apps: 5  ·  units: 8  ·  relations: 3
╰────────────────────────────────╯
 Clouds  Controllers  Models  Status  Relation Data

  NAME          TYPE        REGION       STATUS
  aws-cloud     ec2         us-east-1    ●
  my-openstack  openstack   —            ●
```

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv)
- Juju installed and configured (`juju` CLI working)

## Installation

```bash
uv tool install jujumate
```

## Usage

```bash
jujumate
```

JujuMate reads your existing Juju configuration from `~/.local/share/juju/` automatically — no extra setup needed.

## Keybindings

| Key | Action |
|-----|--------|
| `c` | Clouds |
| `C` | Controllers |
| `m` | Models |
| `s` | Status |
| `↑↓` | Navigate rows |
| `Enter` | Drill-down |
| `Esc` | Clear filter |
| `r` | Refresh |
| `?` | Help |
| `q` | Quit |

## Configuration

JujuMate is configured via `~/.config/jujumate/config.yaml`. All fields are optional.

```yaml
# ~/.config/jujumate/config.yaml

theme: ubuntu               # Theme to use (default: ubuntu)
refresh_interval: 5         # Seconds between auto-refresh (default: 5)
default_controller: prod    # Controller to connect to (default: current Juju controller)
log_file: ~/.local/state/jujumate/jujumate.log
log_level: WARNING          # DEBUG | INFO | WARNING | ERROR | CRITICAL
```

## Themes

JujuMate ships with two built-in themes: `ubuntu` (default) and `dark`.

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

Available theme fields: `primary`, `secondary`, `accent`, `background`, `surface`, `panel`, `warning`, `error`, `success`, `foreground`, `dark`.

User themes override built-in themes with the same name.
