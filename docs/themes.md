# Themes

JujuMate ships with five built-in themes and supports fully custom themes via YAML.

Press `T` at any time to open the **live theme switcher** and preview themes without restarting.

---

## Built-in themes

| Name | Description |
|------|-------------|
| `ubuntu` | Ubuntu brand colours — orange primary *(default)* |
| `dark` | Clean dark theme |
| `monokai` | Monokai-inspired palette |
| `solarized-dark` | Solarized dark palette |
| `spacemacs` | Spacemacs-inspired colours |

---

## Custom themes

Add a YAML file to `~/.config/jujumate/themes/`:

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
# ~/.config/jujumate/config.yaml
theme: mytheme
```

### Available fields

| Field | Description |
|-------|-------------|
| `name` | Theme identifier (must match the filename without `.yaml`) |
| `primary` | Primary UI colour (buttons, highlights) |
| `secondary` | Secondary colour |
| `accent` | Accent colour |
| `background` | Main background colour |
| `surface` | Surface/panel background colour |
| `panel` | Panel colour |
| `warning` | Warning status colour |
| `error` | Error status colour |
| `success` | Success status colour |
| `foreground` | Default text colour |
| `dark` | `true` for dark theme, `false` for light |

!!! tip
    User themes with the same name as a built-in theme will **override** the built-in.
