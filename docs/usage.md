# Usage

## Keyboard shortcuts

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
| `y` | Copy value to clipboard (Relation Data / Secrets) |
| `Esc` | Close modal |

### Log viewer

| Key | Action |
|-----|--------|
| `l` | Cycle log level (DEBUG → INFO → WARNING → ERROR) |
| `/` | Open filter bar |
| `y` | Copy log to clipboard |
| `Enter` | Insert visual separator |
| `End` | Scroll to bottom |
| `Esc` | Clear filter / close |

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

Press `Enter` on any app to open its [Config viewer](#app-config-viewer), or on any relation to open the [Relation Data inspector](#relation-data-inspector).

### Offers browser (`Shift+O`)

Lists all offers across every model in the current controller. Select an offer to see:

- Model, URL, application, charm, description and access level
- Endpoint details (name, interface, role)
- Live consumer list — scans all known controllers to find which models and applications are consuming the offer

### Secrets browser (`Shift+S`)

Lists all secrets visible in the current model. Select a secret to see its metadata: owner, revision, rotation policy and timestamps.

### Live Log viewer (`Shift+L`)

Streams model logs in real time via WebSocket — equivalent to `juju debug-log`. Features:

- Colour-coded log levels (ERROR red, WARNING orange, INFO green, DEBUG cyan)
- Filter by any text — matching words are highlighted in the log
- Cycle minimum log level with `l`
- Timestamps converted to local timezone
- Copy logs to clipboard with `y`

### Relation Data inspector

Press `Enter` on any relation in the Status tab to open a databag viewer showing the application-level and unit-level relation data for both sides of the relation.

### App Config viewer

Press `Enter` on any application in the Status tab to inspect its current configuration values.

---

## Drill-down navigation

1. Select a **controller** and press `Enter` → models are filtered to that controller
2. Select a **model** and press `Enter` → Status tab shows that model's full status
3. Press `Esc` to clear the filter and return to the full view
