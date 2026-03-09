# Installation

## Requirements

- Python **3.10** or later
- A working [Juju](https://juju.is/docs/juju/install-juju) installation (`~/.local/share/juju/` populated)

JujuMate reads your Juju credentials automatically from `~/.local/share/juju/` — the same directory used by the `juju` CLI. No additional configuration is needed.

---

## Install

=== "uv (recommended)"

    ```bash
    uv tool install jujumate
    ```

    [uv](https://docs.astral.sh/uv) is the fastest way to install and run Python tools in isolated environments.

=== "pipx"

    ```bash
    pipx install jujumate
    ```

=== "pip"

    ```bash
    pip install jujumate
    ```

---

## Run

```bash
jujumate
```

On first launch JujuMate connects to your current Juju controller and auto-selects your current model.

---

## Install from source

```bash
git clone https://github.com/Abuelodelanada/jujumate.git
cd jujumate
uv sync
uv run jujumate
```

---

## Upgrade

=== "uv"

    ```bash
    uv tool upgrade jujumate
    ```

=== "pipx"

    ```bash
    pipx upgrade jujumate
    ```
