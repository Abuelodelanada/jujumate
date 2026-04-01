# Configuration

JujuMate is configured via `~/.config/jujumate/config.yaml`. All fields are optional — the app works without a config file using sensible defaults.

```yaml
# ~/.config/jujumate/config.yaml

theme: ubuntu               # Theme name (default: ubuntu)
refresh_interval: 5         # Seconds between auto-refresh (default: 5)
offers_cache_ttl: 300       # Seconds to cache the offers list (default: 300)
default_controller: prod    # Controller to use (default: current Juju controller)
log_file: ~/.local/state/jujumate/jujumate.log
log_level: INFO             # DEBUG | INFO | WARNING | ERROR | CRITICAL
```

## Options

| Field | Default | Description |
|-------|---------|-------------|
| `theme` | `ubuntu` | Name of the active theme. Can be a built-in or custom theme. |
| `refresh_interval` | `5` | Seconds between automatic data refreshes. |
| `offers_cache_ttl` | `300` | Seconds before the offers list cache expires. When the modal is opened within this window, cached data is shown instantly. Press `r` inside the modal to force an immediate refresh. |
| `default_controller` | *(current)* | Juju controller to connect to on startup. If omitted, uses the controller set as current by `juju switch`. |
| `log_file` | *(none)* | Path to JujuMate's own log file. Supports `~` expansion. |
| `log_level` | `INFO` | Logging verbosity for JujuMate's internal logs. |

!!! note
    JujuMate reads Juju credentials from `~/.local/share/juju/` automatically. No Juju-specific credentials need to be configured here.
