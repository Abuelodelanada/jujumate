"""MkDocs build hook: replace the generated index.html with the custom landing page."""

import os
import re
import shutil


def _read_version() -> str:
    with open("pyproject.toml") as f:
        content = f.read()
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    return f"v{match.group(1)}" if match else "v?"


def on_post_build(config: dict) -> None:
    site_dir = config["site_dir"]
    version = _read_version()

    landing = open("landing/index.html").read().replace("__VERSION__", version)
    with open(os.path.join(site_dir, "index.html"), "w") as f:
        f.write(landing)

    shutil.copy("landing/landing.css", os.path.join(site_dir, "landing.css"))
    shutil.copy("icon.svg", os.path.join(site_dir, "icon.svg"))
    os.makedirs(os.path.join(site_dir, "assets"), exist_ok=True)
    shutil.copy("icon.svg", os.path.join(site_dir, "assets", "icon.svg"))
